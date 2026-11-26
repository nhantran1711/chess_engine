//! Engine-vs-engine match runner with SPRT, for testing whether a change gains Elo.
//!
//!     chessgame arena NEW.exe BASE.exe [--tc 5+0.05] [--concurrency 10] [--games 20000]
//!                     [--openings match/openings.epd] [--plies 4] [--sprt ELO0 ELO1] [--option-a NAME=VALUE]...
//!
//! Openings: a random line from the EPD file plus `--plies` random legal moves, kept only if the
//! static evaluation stays within 150 cp. Each opening is played twice with colours reversed
//! (a "pair"), which cancels most of the opening's bias.
//!
//! The arbiter is this crate's move generator: it checks legality and ends games on mate,
//! stalemate, threefold repetition, the fifty-move rule and insufficient material. A game is
//! adjudicated as a win once both engines report >= 1000 cp for the same side for 4 plies each,
//! and as a draw after move 40 once both report |score| <= 10 for 8 plies each. Clocks are kept
//! by wall time between "go" and "bestmove"; running out of time loses.
//!
//! SPRT (alpha = beta = 0.05) on the pentanomial pair results, normalised as in fishtest's
//! "logistic" approximation: H0 = ELO0, H1 = ELO1 Elo. Stops once the log-likelihood ratio leaves
//! (-2.94, 2.94), but not before 100 pairs. Without --sprt it plays --games games and prints the Elo with a 95% interval.

use crate::board::*;
use crate::eval::evaluate_white;
use crate::movegen::legal_moves;
use crate::moves::*;
use std::collections::HashMap;
use std::io::{BufRead, BufReader, Write};
use std::process::{Child, ChildStdin, ChildStdout, Command, Stdio};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Instant;

/// SPRT may not stop before this many pairs
const MIN_SPRT_PAIRS: u64 = 100;

struct Config {
    engines: [String; 2],
    options: [Vec<(String, String)>; 2],
    base_ms: f64,
    inc_ms: f64,
    concurrency: usize,
    max_games: u64,
    openings: Vec<String>,
    plies: usize,
    sprt: Option<(f64, f64)>,
}

struct Engine {
    child: Child,
    stdin: ChildStdin,
    stdout: BufReader<ChildStdout>,
}

impl Engine {
    fn start(path: &str, options: &[(String, String)]) -> Engine {
        let mut child = Command::new(path)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::null())
            .spawn()
            .unwrap_or_else(|e| panic!("cannot start {path}: {e}"));
        let stdin = child.stdin.take().unwrap();
        let stdout = BufReader::new(child.stdout.take().unwrap());
        let mut e = Engine { child, stdin, stdout };
        e.send("uci");
        e.wait_for("uciok");
        for (name, value) in options {
            e.send(&format!("setoption name {name} value {value}"));
        }
        e.send("isready");
        e.wait_for("readyok");
        e
    }

    fn send(&mut self, line: &str) {
        writeln!(self.stdin, "{line}").ok();
        self.stdin.flush().ok();
    }

    /// Reads lines until one starts with `prefix`; returns it and the last reported score
    fn wait_for(&mut self, prefix: &str) -> (String, Option<i32>) {
        let mut score = None;
        let mut line = String::new();
        loop {
            line.clear();
            if self.stdout.read_line(&mut line).unwrap_or(0) == 0 {
                return (String::new(), score); // Engine died
            }
            if line.starts_with(prefix) {
                return (line.trim().to_string(), score);
            }
            if line.starts_with("info") {
                let t: Vec<&str> = line.split_whitespace().collect();
                if let Some(i) = t.iter().position(|&x| x == "score") {
                    match (t.get(i + 1), t.get(i + 2).and_then(|v| v.parse::<i32>().ok())) {
                        (Some(&"cp"), Some(v)) => score = Some(v),
                        (Some(&"mate"), Some(v)) => score = Some(if v > 0 { 30000 } else { -30000 }),
                        _ => {}
                    }
                }
            }
        }
    }
}

impl Drop for Engine {
    fn drop(&mut self) {
        self.send("quit");
        let _ = self.child.wait();
    }
}

struct Rng(u64);
impl Rng {
    fn next(&mut self) -> u64 {
        self.0 ^= self.0 << 13;
        self.0 ^= self.0 >> 7;
        self.0 ^= self.0 << 17;
        self.0
    }
}

/// (FEN, moves): a book line plus random plies, roughly balanced
fn random_opening(cfg: &Config, rng: &mut Rng) -> (String, Vec<Move>) {
    loop {
        let fen = format!("{} 0 1", cfg.openings[(rng.next() % cfg.openings.len() as u64) as usize]);
        let mut b = Board::from_fen(&fen).unwrap();
        let mut line = Vec::new();
        let mut ok = true;
        for _ in 0..cfg.plies {
            let moves = legal_moves(&b);
            if moves.is_empty() {
                ok = false;
                break;
            }
            let m = moves[(rng.next() % moves.len() as u64) as usize];
            line.push(m);
            b = b.make_move(m);
        }
        if ok && !legal_moves(&b).is_empty() && evaluate_white(&b).abs() <= 150 {
            return (fen, line);
        }
    }
}

fn insufficient(b: &Board) -> bool {
    let heavy = b.pieces[PAWN] | b.pieces[ROOK] | b.pieces[QUEEN];
    if heavy != 0 {
        return false;
    }
    let minors = (b.pieces[KNIGHT] | b.pieces[BISHOP]).count_ones();
    minors <= 1
}

/// Result for White: 2 win, 1 draw, 0 loss
fn play_game(cfg: &Config, white: &mut Engine, black: &mut Engine, fen: &str, opening: &[Move]) -> (u8, &'static str) {
    let mut b = Board::from_fen(fen).unwrap();
    let mut moves: Vec<String> = Vec::new();
    let mut counts: HashMap<u64, u32> = HashMap::new();
    for &m in opening {
        moves.push(to_uci(m));
        b = b.make_move(m);
    }
    *counts.entry(b.hash).or_default() += 1;
    let mut clock = [cfg.base_ms, cfg.base_ms];
    // Last scores from White's point of view, per side
    let mut scores: [Vec<i32>; 2] = [Vec::new(), Vec::new()];
    white.send("ucinewgame");
    black.send("ucinewgame");
    for e in [&mut *white, &mut *black] {
        e.send("isready");
        e.wait_for("readyok");
    }
    let mut ply = 0;
    loop {
        let legal = legal_moves(&b);
        if legal.is_empty() {
            return if b.in_check() { (if b.side == WHITE { 0 } else { 2 }, "mate") } else { (1, "stalemate") };
        }
        if b.halfmove >= 100 {
            return (1, "fifty moves");
        }
        if counts[&b.hash] >= 3 {
            return (1, "repetition");
        }
        if insufficient(&b) {
            return (1, "insufficient material");
        }
        if ply >= 600 {
            return (1, "ply cap");
        }
        let side = b.side;
        let e: &mut Engine = if side == WHITE { &mut *white } else { &mut *black };
        let pos = if moves.is_empty() { format!("position fen {fen}") } else { format!("position fen {fen} moves {}", moves.join(" ")) };
        e.send(&pos);
        let go = format!(
            "go wtime {:.0} btime {:.0} winc {:.0} binc {:.0}",
            clock[WHITE].max(1.0),
            clock[BLACK].max(1.0),
            cfg.inc_ms,
            cfg.inc_ms
        );
        let t = Instant::now();
        e.send(&go);
        let (line, score) = e.wait_for("bestmove");
        let used = t.elapsed().as_secs_f64() * 1000.0;
        clock[side] -= used;
        if clock[side] < 0.0 {
            return (if side == WHITE { 0 } else { 2 }, "time");
        }
        clock[side] += cfg.inc_ms;
        let uci = line.split_whitespace().nth(1).unwrap_or("");
        let Some(m) = legal.iter().copied().find(|&m| to_uci(m) == uci) else {
            return (if side == WHITE { 0 } else { 2 }, "illegal move");
        };
        if let Some(s) = score {
            scores[side].push(if side == WHITE { s } else { -s });
        } else {
            scores[side].clear();
        }
        moves.push(uci.to_string());
        b = b.make_move(m);
        *counts.entry(b.hash).or_default() += 1;
        ply += 1;

        let last = |v: &Vec<i32>, n: usize| -> Option<Vec<i32>> { if v.len() >= n { Some(v[v.len() - n..].to_vec()) } else { None } };
        if let (Some(w), Some(bl)) = (last(&scores[WHITE], 4), last(&scores[BLACK], 4)) {
            if w.iter().chain(bl.iter()).all(|&s| s >= 1000) {
                return (2, "adjudicated");
            }
            if w.iter().chain(bl.iter()).all(|&s| s <= -1000) {
                return (0, "adjudicated");
            }
        }
        if ply >= 80 {
            if let (Some(w), Some(bl)) = (last(&scores[WHITE], 8), last(&scores[BLACK], 8)) {
                if w.iter().chain(bl.iter()).all(|&s| s.abs() <= 10) {
                    return (1, "draw adjudicated");
                }
            }
        }
    }
}

/// Pentanomial counts: index = engine A's points in the pair, in half points (0..=4)
#[derive(Default, Clone, Copy)]
struct Stats {
    penta: [u64; 5],
    wdl: [u64; 3], // A's wins, draws, losses
}

fn elo_from_score(s: f64) -> f64 {
    let s = s.clamp(1e-6, 1.0 - 1e-6);
    -400.0 * (1.0 / s - 1.0).log10()
}

fn score_from_elo(e: f64) -> f64 {
    1.0 / (1.0 + 10f64.powf(-e / 400.0))
}

/// Pentanomial GSPRT log-likelihood ratio (as in fishtest)
fn llr(st: &Stats, elo0: f64, elo1: f64) -> f64 {
    let n: u64 = st.penta.iter().sum();
    if n == 0 {
        return 0.0;
    }
    let n = n as f64;
    // Add a tiny prior so a category with zero count doesn't make the variance zero
    let probs: Vec<f64> = st.penta.iter().map(|&c| (c as f64 + 1e-3) / (n + 5e-3)).collect();
    let mean: f64 = probs.iter().enumerate().map(|(i, p)| p * i as f64 / 4.0).sum();
    let var: f64 = probs.iter().enumerate().map(|(i, p)| p * (i as f64 / 4.0 - mean).powi(2)).sum();
    if var <= 0.0 {
        return 0.0;
    }
    let (s0, s1) = (score_from_elo(elo0), score_from_elo(elo1));
    n * (s1 - s0) * (2.0 * mean - s0 - s1) / (2.0 * var)
}

fn report(st: &Stats) -> String {
    let games = st.wdl.iter().sum::<u64>() as f64;
    let pairs: u64 = st.penta.iter().sum();
    let score = (st.wdl[0] as f64 + 0.5 * st.wdl[1] as f64) / games.max(1.0);
    // Interval from the pair variance
    let mean: f64 = st.penta.iter().enumerate().map(|(i, &c)| c as f64 * i as f64 / 4.0).sum::<f64>() / pairs.max(1) as f64;
    let var: f64 = st.penta.iter().enumerate().map(|(i, &c)| c as f64 * (i as f64 / 4.0 - mean).powi(2)).sum::<f64>() / pairs.max(1) as f64;
    let margin = 1.96 * (var / pairs.max(1) as f64).sqrt();
    format!(
        "games {} +{} ={} -{}  score {:.3}  elo {:+.1} (95% {:+.1} .. {:+.1})  penta {:?}",
        games,
        st.wdl[0],
        st.wdl[1],
        st.wdl[2],
        score,
        elo_from_score(score),
        elo_from_score(mean - margin),
        elo_from_score(mean + margin),
        st.penta
    )
}

pub fn run(args: &[String]) {
    let mut engines = Vec::new();
    let mut options: [Vec<(String, String)>; 2] = [Vec::new(), Vec::new()];
    let mut tc = "5+0.05".to_string();
    let mut concurrency = 10;
    let mut max_games = 20000;
    let mut openings_path = "match/openings.epd".to_string();
    let mut plies = 4;
    let mut sprt = None;
    let mut i = 0;
    while i < args.len() {
        let a = args[i].as_str();
        let val = |k: usize| args.get(i + k).cloned().unwrap_or_default();
        match a {
            "--tc" => {
                tc = val(1);
                i += 1;
            }
            "--concurrency" => {
                concurrency = val(1).parse().unwrap();
                i += 1;
            }
            "--games" => {
                max_games = val(1).parse().unwrap();
                i += 1;
            }
            "--openings" => {
                openings_path = val(1);
                i += 1;
            }
            "--plies" => {
                plies = val(1).parse().unwrap();
                i += 1;
            }
            "--sprt" => {
                sprt = Some((val(1).parse().unwrap(), val(2).parse().unwrap()));
                i += 2;
            }
            "--option-a" | "--option-b" => {
                let v = val(1);
                let (k, x) = v.split_once('=').expect("NAME=VALUE");
                options[if a == "--option-a" { 0 } else { 1 }].push((k.to_string(), x.to_string()));
                i += 1;
            }
            _ => engines.push(a.to_string()),
        }
        i += 1;
    }
    assert!(engines.len() == 2, "need two engine paths");
    let (base, inc) = tc.split_once('+').unwrap_or((&tc, "0"));
    let openings: Vec<String> = std::fs::read_to_string(&openings_path)
        .expect("openings file")
        .lines()
        .map(|l| l.split(';').next().unwrap().split_whitespace().take(4).collect::<Vec<_>>().join(" "))
        .filter(|l| !l.is_empty())
        .collect();
    let cfg = Arc::new(Config {
        engines: [engines[0].clone(), engines[1].clone()],
        options,
        base_ms: base.parse::<f64>().unwrap() * 1000.0,
        inc_ms: inc.parse::<f64>().unwrap() * 1000.0,
        concurrency,
        max_games,
        openings,
        plies,
        sprt,
    });
    println!("A = {}\nB = {}\ntc {tc}, concurrency {concurrency}, sprt {:?}", cfg.engines[0], cfg.engines[1], cfg.sprt);

    let stats = Arc::new(Mutex::new(Stats::default()));
    let done = Arc::new(AtomicBool::new(false));
    let pairs_started = Arc::new(AtomicU64::new(0));
    let seed = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos() as u64 | 1;
    let mut handles = Vec::new();
    for t in 0..cfg.concurrency {
        let (cfg, stats, done, pairs_started) = (cfg.clone(), stats.clone(), done.clone(), pairs_started.clone());
        handles.push(std::thread::spawn(move || {
            let mut rng = Rng(seed ^ ((t as u64 + 1) * 0x9E3779B97F4A7C15));
            let mut a = Engine::start(&cfg.engines[0], &cfg.options[0]);
            let mut b = Engine::start(&cfg.engines[1], &cfg.options[1]);
            while !done.load(Ordering::Relaxed) {
                if pairs_started.fetch_add(1, Ordering::Relaxed) * 2 >= cfg.max_games {
                    break;
                }
                let (fen, line) = random_opening(&cfg, &mut rng);
                let (r1, why1) = play_game(&cfg, &mut a, &mut b, &fen, &line); // A white
                let (r2, why2) = play_game(&cfg, &mut b, &mut a, &fen, &line); // A black
                let a1 = r1 as usize; // A's half points as White
                let a2 = 2 - r2 as usize;
                let mut st = stats.lock().unwrap();
                st.penta[a1 + a2] += 1;
                for p in [a1, a2] {
                    st.wdl[2 - p] += 1;
                }
                for why in [why1, why2] {
                    if matches!(why, "time" | "illegal move") {
                        println!("warning: game ended by {why}");
                    }
                }
                let pairs: u64 = st.penta.iter().sum();
                if pairs % 20 == 0 {
                    let l = cfg.sprt.map(|(e0, e1)| format!("  llr {:.2}", llr(&st, e0, e1))).unwrap_or_default();
                    println!("{}{l}", report(&st));
                }
                if let Some((e0, e1)) = cfg.sprt {
                    // With few pairs the variance estimate is unreliable (near zero if they all
                    // agree), which would send the LLR past a bound by chance
                    let l = llr(&st, e0, e1);
                    if pairs >= MIN_SPRT_PAIRS && l.abs() >= 2.944 {
                        done.store(true, Ordering::Relaxed);
                    }
                }
            }
        }));
    }
    for h in handles {
        h.join().ok();
    }
    let st = stats.lock().unwrap();
    println!("\nFINAL {}", report(&st));
    if let Some((e0, e1)) = cfg.sprt {
        let l = llr(&st, e0, e1);
        println!("SPRT [{e0}, {e1}] llr {l:.2}: {}", if l >= 2.944 { "H1 accepted (gain)" } else if l <= -2.944 { "H0 accepted (no gain)" } else { "inconclusive" });
    }
}
