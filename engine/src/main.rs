//! UCI front end, matching ChessGame/UCI.py.
//!
//!     chessgame                 # UCI mode
//!     chessgame bench [depth]   # fixed-depth search over a few positions, prints nodes and nps
//!
//! Supported commands: uci, isready, ucinewgame, position [startpos | fen <fen>] [moves ...],
//! go [wtime btime winc binc movestogo movetime depth nodes infinite perft], stop, quit,
//! and "eval" (prints the static evaluation, White's point of view).
//! The search runs on a background thread so "stop" and "isready" are answered while it thinks.

mod attacks;
mod board;
mod eval;
mod movegen;
mod moves;
mod search;
mod zobrist;

use board::*;
use moves::*;
use search::*;
use std::io::{self, BufRead, Write};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::thread::{self, JoinHandle};
use std::time::{Duration, Instant};

const ENGINE_NAME: &str = "ChessGame";
const ENGINE_AUTHOR: &str = "nhantran1711";
const MOVE_OVERHEAD: f64 = 0.05; // Seconds kept back per move for GUI latency
const DEFAULT_MOVES_TO_GO: f64 = 30.0;

// Centipawns as is, mate scores -> "mate N" in moves (negative when getting mated)
fn score_to_uci(score: i32) -> String {
    if score >= MATE_BOUND {
        format!("mate {}", (CHECKMATE - score + 1) / 2)
    } else if score <= -MATE_BOUND {
        format!("mate -{}", (CHECKMATE + score) / 2)
    } else {
        format!("cp {score}")
    }
}

fn print_info(info: &Info) {
    let ms = info.elapsed.as_millis().max(1);
    let nps = info.nodes as u128 * 1000 / ms;
    let pv: Vec<String> = info.pv.iter().map(|&m| to_uci(m)).collect();
    println!(
        "info depth {} score {} nodes {} nps {} time {} pv {}",
        info.depth,
        score_to_uci(info.score),
        info.nodes,
        nps,
        ms,
        pv.join(" ")
    );
}

#[derive(Default)]
struct GoParams {
    wtime: Option<f64>,
    btime: Option<f64>,
    winc: Option<f64>,
    binc: Option<f64>,
    movestogo: Option<f64>,
    movetime: Option<f64>,
    depth: Option<i32>,
    nodes: Option<u64>,
    perft: Option<u32>,
    infinite: bool,
}

fn parse_go(tokens: &[&str]) -> GoParams {
    let mut p = GoParams::default();
    let mut i = 0;
    while i < tokens.len() {
        let value = tokens.get(i + 1).copied().unwrap_or("");
        let num = value.parse::<f64>().ok();
        match tokens[i] {
            "infinite" => p.infinite = true,
            "wtime" => p.wtime = num,
            "btime" => p.btime = num,
            "winc" => p.winc = num,
            "binc" => p.binc = num,
            "movestogo" => p.movestogo = num,
            "movetime" => p.movetime = num,
            "depth" => p.depth = value.parse().ok(),
            "nodes" => p.nodes = value.parse().ok(),
            "perft" => p.perft = value.parse().ok(),
            _ => {
                i += 1;
                continue;
            }
        }
        i += if tokens[i] == "infinite" { 1 } else { 2 };
    }
    p
}

// Seconds to spend on this move, or None for no time limit
fn allocate_time(p: &GoParams, white: bool) -> Option<f64> {
    if let Some(movetime) = p.movetime {
        return Some((movetime / 1000.0 - MOVE_OVERHEAD).max(0.01));
    }
    let remaining = if white { p.wtime } else { p.btime }?;
    let increment = if white { p.winc } else { p.binc }.unwrap_or(0.0);
    let moves_to_go = p.movestogo.unwrap_or(DEFAULT_MOVES_TO_GO).max(1.0);
    let budget = (remaining / moves_to_go + increment * 0.75).min(remaining * 0.5);
    Some((budget / 1000.0 - MOVE_OVERHEAD).max(0.01))
}

fn set_position(tokens: &[&str]) -> Board {
    let split = tokens.iter().position(|&t| t == "moves").unwrap_or(tokens.len());
    let (setup, moves) = (&tokens[..split], tokens.get(split + 1..).unwrap_or(&[]));
    let mut b = if setup.first() == Some(&"fen") {
        match Board::from_fen(&setup[1..].join(" ")) {
            Ok(b) => b,
            Err(e) => {
                println!("info string {e}");
                Board::startpos()
            }
        }
    } else {
        Board::startpos()
    };
    for &notation in moves {
        match movegen::legal_moves(&b).into_iter().find(|&m| to_uci(m) == notation) {
            Some(m) => b = b.make_move(m),
            None => {
                println!("info string illegal move {notation}, ignoring the rest");
                break;
            }
        }
    }
    b
}

struct Engine {
    board: Board,
    stop: Arc<AtomicBool>,
    searcher: Option<Searcher>,
    thread: Option<JoinHandle<Searcher>>,
}

impl Engine {
    fn stop_search(&mut self) {
        if let Some(handle) = self.thread.take() {
            self.stop.store(true, Ordering::Relaxed);
            self.searcher = Some(handle.join().expect("search thread panicked"));
        }
    }

    fn go(&mut self, p: GoParams) {
        if let Some(depth) = p.perft {
            let start = Instant::now();
            let nodes = movegen::perft(&self.board, depth);
            let secs = start.elapsed().as_secs_f64();
            println!("info string perft {depth}: {nodes} nodes in {secs:.2}s ({:.0} nps)", nodes as f64 / secs.max(1e-9));
            println!("{nodes}");
            return;
        }
        let time = if p.infinite { None } else { allocate_time(&p, self.board.side == WHITE) };
        let limits = Limits {
            time: time.map(Duration::from_secs_f64),
            depth: p.depth.unwrap_or(MAX_DEPTH).clamp(1, MAX_DEPTH),
            nodes: p.nodes,
        };
        let infinite = p.infinite;
        let board = self.board;
        let stop = self.stop.clone();
        stop.store(false, Ordering::Relaxed);
        let mut searcher = self.searcher.take().unwrap();
        self.thread = Some(thread::spawn(move || {
            let m = searcher.search(&board, limits, &mut |info| print_info(info));
            // "go infinite" must not report a move until the GUI sends stop
            while infinite && !stop.load(Ordering::Relaxed) {
                thread::sleep(Duration::from_millis(1));
            }
            println!("bestmove {}", to_uci(m));
            io::stdout().flush().ok();
            searcher
        }));
    }
}

fn bench(depth: i32) {
    const POSITIONS: [&str; 6] = [
        START_FEN,
        "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1",
        "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1",
        "r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1",
        "rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8",
        "r4rk1/1pp1qppp/p1np1n2/2b1p1B1/2B1P1b1/P1NP1N2/1PP1QPPP/R4RK1 w - - 0 10",
    ];
    let mut total = 0;
    let start = Instant::now();
    for fen in POSITIONS {
        let mut s = Searcher::new(Arc::new(AtomicBool::new(false)));
        let t = Instant::now();
        let m = s.search(&Board::from_fen(fen).unwrap(), Limits { depth, ..Limits::default() }, &mut |_| {});
        println!("{:>10} nodes {:>7.2}s  {}  {}", s.nodes, t.elapsed().as_secs_f64(), to_uci(m), fen);
        total += s.nodes;
    }
    let secs = start.elapsed().as_secs_f64();
    println!("depth {depth}: {total} nodes {:.2}s {:.0} nps", secs, total as f64 / secs);
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.get(1).map(String::as_str) == Some("bench") {
        bench(args.get(2).and_then(|d| d.parse().ok()).unwrap_or(6));
        return;
    }

    let stop = Arc::new(AtomicBool::new(false));
    let mut engine = Engine { board: Board::startpos(), stop: stop.clone(), searcher: Some(Searcher::new(stop)), thread: None };

    for line in io::stdin().lock().lines() {
        let Ok(line) = line else { break };
        let tokens: Vec<&str> = line.split_whitespace().collect();
        match tokens.first().copied() {
            Some("uci") => {
                println!("id name {ENGINE_NAME}");
                println!("id author {ENGINE_AUTHOR}");
                println!("uciok");
            }
            Some("isready") => println!("readyok"),
            Some("ucinewgame") => {
                engine.stop_search();
                engine.searcher = Some(Searcher::new(engine.stop.clone())); // Fresh transposition table
            }
            Some("position") => {
                engine.stop_search();
                engine.board = set_position(&tokens[1..]);
            }
            Some("go") => {
                engine.stop_search();
                engine.go(parse_go(&tokens[1..]));
            }
            Some("stop") => engine.stop_search(),
            Some("eval") => println!("{}", eval::evaluate_white(&engine.board)),
            Some("quit") => break,
            _ => {} // debug, setoption, register, ponderhit: accepted and ignored
        }
        io::stdout().flush().ok();
    }
    engine.stop_search();
}
