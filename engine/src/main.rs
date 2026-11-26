//! UCI front end, matching ChessGame/UCI.py.
//!
//!     chessgame                 # UCI mode
//!     chessgame bench [depth]   # fixed-depth search over a few positions, prints nodes and nps
//!     chessgame tune positions.epd [epochs]   # Texel-tune the evaluation, writes src/params.rs
//!     chessgame arena NEW BASE [--tc 5+0.05] [--sprt 0 5] ...   # engine-vs-engine match (see arena.rs)
//!
//! Supported commands: `uci`, `isready`, `ucinewgame`, `position [startpos | fen <fen>] [moves ...]`,
//! `go [wtime btime winc binc movestogo movetime depth nodes infinite perft]`, `stop`, `quit`,
//! and `eval` (prints the static evaluation, White's point of view).
//! The search runs on a background thread so "stop" and "isready" are answered while it thinks.

mod arena;
mod attacks;
mod board;
mod eval;
mod movegen;
mod moves;
mod params;
mod search;
mod see;
mod tune;
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
const DEFAULT_MOVES_TO_GO: f64 = 25.0;
const DEFAULT_HASH_MB: usize = 32;

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

/// (soft, hard) seconds for this move, or None for no time limit. The soft target is a share of
/// remaining / moves-to-go plus most of the increment; the search scales it by how stable the
/// best move is (see `Searcher::search`) and never runs past the hard limit, a few times the
/// target but at most a fifth of the clock. MOVE_OVERHEAD is kept back for GUI and pipe latency.
fn allocate_time(p: &GoParams, white: bool) -> Option<(f64, f64)> {
    if let Some(movetime) = p.movetime {
        let t = (movetime / 1000.0 - MOVE_OVERHEAD).max(0.01);
        return Some((t, t));
    }
    let remaining = if white { p.wtime } else { p.btime }? / 1000.0;
    let increment = if white { p.winc } else { p.binc }.unwrap_or(0.0) / 1000.0;
    let usable = (remaining - MOVE_OVERHEAD).max(0.01);
    let moves_to_go = p.movestogo.unwrap_or(DEFAULT_MOVES_TO_GO).max(1.0);
    let budget = (usable / moves_to_go + increment * 0.75).min(usable * 0.5);
    let hard = (budget * 3.0).min(usable * if p.movestogo == Some(1.0) { 0.9 } else { 0.2 }).max(budget.min(usable));
    Some((budget * 0.6, hard))
}

/// The position after `position ...`, and the hashes of every earlier position in the game
/// (for repetition detection)
fn set_position(tokens: &[&str]) -> (Board, Vec<u64>) {
    let split = tokens.iter().position(|&t| t == "moves").unwrap_or(tokens.len());
    let (setup, moves) = (&tokens[..split], tokens.get(split + 1..).unwrap_or(&[]));
    let mut history = Vec::new();
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
            Some(m) => {
                history.push(b.hash);
                b = b.make_move(m);
            }
            None => {
                println!("info string illegal move {notation}, ignoring the rest");
                break;
            }
        }
    }
    (b, history)
}

/// UCI state. The searcher is moved into the search thread and handed back when it finishes,
/// so exactly one of `searcher` and `thread` is Some at any time. Ownership moving between
/// threads avoids a mutex around the transposition table.
struct Engine {
    board: Board,
    /// Hashes of the positions before `board` in this game
    history: Vec<u64>,
    /// Shared with the search thread, which polls it to know when to stop
    stop: Arc<AtomicBool>,
    searcher: Option<Searcher>,
    thread: Option<JoinHandle<Searcher>>,
    hash_mb: usize,
}

impl Engine {
    /// Stops any running search and waits for it. Safe to call when nothing is running.
    /// Every command that touches the board or searcher calls this first.
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
            soft: time.map(|t| Duration::from_secs_f64(t.0)),
            time: time.map(|t| Duration::from_secs_f64(t.1)),
            depth: p.depth.unwrap_or(MAX_DEPTH).clamp(1, MAX_DEPTH),
            nodes: p.nodes,
        };
        let infinite = p.infinite;
        let board = self.board;
        let history = self.history.clone();
        let stop = self.stop.clone();
        stop.store(false, Ordering::Relaxed);
        let mut searcher = self.searcher.take().unwrap();
        self.thread = Some(thread::spawn(move || {
            let m = searcher.search(&board, &history, limits, &mut |info| print_info(info));
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
        let m = s.search(&Board::from_fen(fen).unwrap(), &[], Limits { depth, ..Limits::default() }, &mut |_| {});
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
    if args.get(1).map(String::as_str) == Some("tune") {
        tune::run(&args[2..]);
        return;
    }
    if args.get(1).map(String::as_str) == Some("arena") {
        arena::run(&args[2..]);
        return;
    }

    let stop = Arc::new(AtomicBool::new(false));
    let mut engine = Engine {
        board: Board::startpos(),
        history: Vec::new(),
        stop: stop.clone(),
        searcher: Some(Searcher::with_hash(stop, DEFAULT_HASH_MB)),
        thread: None,
        hash_mb: DEFAULT_HASH_MB,
    };

    for line in io::stdin().lock().lines() {
        let Ok(line) = line else { break };
        let tokens: Vec<&str> = line.split_whitespace().collect();
        match tokens.first().copied() {
            Some("uci") => {
                println!("id name {ENGINE_NAME}");
                println!("id author {ENGINE_AUTHOR}");
                println!("option name Hash type spin default {DEFAULT_HASH_MB} min 1 max 65536");
                println!("uciok");
            }
            Some("isready") => println!("readyok"),
            Some("ucinewgame") => {
                engine.stop_search();
                engine.searcher = Some(Searcher::with_hash(engine.stop.clone(), engine.hash_mb)); // Fresh transposition table
            }
            Some("setoption") => {
                // setoption name <name> value <value>
                let name = tokens.iter().position(|&t| t == "name").and_then(|i| tokens.get(i + 1));
                let value = tokens.iter().position(|&t| t == "value").and_then(|i| tokens.get(i + 1));
                if let (Some(name), Some(value)) = (name, value) {
                    if name.eq_ignore_ascii_case("hash") {
                        if let Ok(mb) = value.parse::<usize>() {
                            engine.stop_search();
                            engine.hash_mb = mb.clamp(1, 65536);
                            engine.searcher = Some(Searcher::with_hash(engine.stop.clone(), engine.hash_mb));
                        }
                    }
                }
            }
            Some("position") => {
                engine.stop_search();
                (engine.board, engine.history) = set_position(&tokens[1..]);
            }
            Some("go") => {
                engine.stop_search();
                engine.go(parse_go(&tokens[1..]));
            }
            Some("stop") => engine.stop_search(),
            Some("eval") => println!("{}", eval::evaluate_white(&engine.board)),
            Some("quit") => break,
            _ => {} // debug, register, ponderhit: accepted and ignored
        }
        io::stdout().flush().ok();
    }
    engine.stop_search();
}
