//! Alpha-beta (negamax) search, ported from `Searcher` in ChessGame/ChessAI.py:
//! iterative deepening, transposition table, quiescence search, and move ordering by
//! hash move, MVV-LVA captures, killer moves and history heuristic.
//!
//! Scores are relative to the side to move. Mate is CHECKMATE - ply, so faster mates score higher.

use crate::board::*;
use crate::eval::evaluate;
use crate::movegen::*;
use crate::moves::*;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};

pub const CHECKMATE: i32 = 100_000;
pub const MAX_PLY: usize = 128;
pub const MAX_DEPTH: i32 = 64;
pub const MATE_BOUND: i32 = CHECKMATE - MAX_PLY as i32;
const INFINITY: i32 = CHECKMATE + 1;

const PV_MOVE_SCORE: i64 = 1_000_000;
const CAPTURE_SCORE: i64 = 100_000;
const KILLER_SCORES: [i64; 2] = [90_000, 80_000];
// Ordering values, separate from evaluation so the king counts as the most valuable attacker
const MVV_LVA_VALUE: [i32; 6] = [1, 3, 3, 5, 9, 10];

const TT_SIZE_BITS: usize = 20;
const TT_EXACT: u8 = 0;
const TT_LOWER: u8 = 1; // score >= stored (beta cutoff)
const TT_UPPER: u8 = 2; // score <= stored (failed low)

#[derive(Clone, Copy, Default)]
struct TTEntry {
    key: u64,
    score: i32,
    mv: Move,
    depth: i8,
    flag: u8,
    age: u8,
}

#[derive(Clone, Copy, Debug)]
pub struct Limits {
    pub time: Option<Duration>,
    pub depth: i32,
    pub nodes: Option<u64>,
}

impl Default for Limits {
    fn default() -> Limits {
        Limits { time: None, depth: MAX_DEPTH, nodes: None }
    }
}

/// Reported after each completed depth
pub struct Info<'a> {
    pub depth: i32,
    pub score: i32,
    pub nodes: u64,
    pub elapsed: Duration,
    pub pv: &'a [Move],
}

pub struct Searcher {
    tt: Vec<TTEntry>, // Survives between searches so the next move reuses this one's work
    tt_age: u8,
    killers: [[Move; 2]; MAX_PLY],
    history: Vec<[i64; 64]>, // [from][to]
    pub nodes: u64,
    pub depth_reached: i32,
    pub best_score: i32,
    start: Instant,
    limits: Limits,
    stop: Arc<AtomicBool>, // Set from another thread to abort the search
    stopped: bool,
    rng: u64,
}

impl Searcher {
    pub fn new(stop: Arc<AtomicBool>) -> Searcher {
        let seed = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_nanos() as u64).unwrap_or(1);
        Searcher {
            tt: vec![TTEntry::default(); 1 << TT_SIZE_BITS],
            tt_age: 0,
            killers: [[NO_MOVE; 2]; MAX_PLY],
            history: vec![[0; 64]; 64],
            nodes: 0,
            depth_reached: 0,
            best_score: 0,
            start: Instant::now(),
            limits: Limits::default(),
            stop,
            stopped: false,
            rng: seed | 1,
        }
    }

    fn reset_tables(&mut self) {
        self.killers = [[NO_MOVE; 2]; MAX_PLY];
        for row in self.history.iter_mut() {
            *row = [0; 64];
        }
        self.nodes = 0;
        self.stopped = false;
    }

    #[inline]
    fn tt_probe(&self, key: u64) -> Option<TTEntry> {
        let entry = self.tt[key as usize & (self.tt.len() - 1)];
        if entry.key == key {
            Some(entry)
        } else {
            None
        }
    }

    // Replace an entry from an older search, or one searched no deeper than this
    #[inline]
    fn tt_store(&mut self, key: u64, depth: i32, flag: u8, score: i32, mv: Move, ply: usize) {
        let index = key as usize & (self.tt.len() - 1);
        let old = self.tt[index];
        if old.age != self.tt_age || depth >= old.depth as i32 {
            self.tt[index] = TTEntry { key, score: score_to_tt(score, ply), mv, depth: depth as i8, flag, age: self.tt_age };
        }
    }

    #[inline]
    fn should_stop(&mut self) -> bool {
        if self.stopped {
            return true;
        }
        if self.nodes & 1023 == 0 {
            if self.stop.load(Ordering::Relaxed) {
                self.stopped = true;
            }
            if let Some(limit) = self.limits.time {
                if self.start.elapsed() > limit {
                    self.stopped = true;
                }
            }
        }
        if let Some(max) = self.limits.nodes {
            if self.nodes >= max {
                self.stopped = true;
            }
        }
        self.stopped
    }

    fn next_random(&mut self) -> u64 {
        self.rng ^= self.rng << 13;
        self.rng ^= self.rng >> 7;
        self.rng ^= self.rng << 17;
        self.rng
    }

    /// Iterative deepening: search depth 1, 2, 3, ... until a limit is hit, keep the last completed
    /// result. Returns NO_MOVE when there are no legal moves.
    pub fn search(&mut self, b: &Board, limits: Limits, on_info: &mut dyn FnMut(&Info)) -> Move {
        self.reset_tables();
        self.tt_age = self.tt_age.wrapping_add(1);
        self.start = Instant::now();
        self.limits = limits;

        let mut root_moves = legal_moves(b);
        if root_moves.is_empty() {
            return NO_MOVE;
        }
        for i in (1..root_moves.len()).rev() {
            // Variety between equally scored moves
            let j = (self.next_random() % (i as u64 + 1)) as usize;
            root_moves.swap(i, j);
        }

        root_moves.sort_by_key(|&m| -self.order_score(b, m, 0, NO_MOVE));
        // Fallback if not even one root move finishes: best capture by MVV-LVA
        let mut best_move = root_moves[0];
        if let Some(entry) = self.tt_probe(b.hash) {
            if root_moves.contains(&entry.mv) {
                best_move = entry.mv;
            }
        }
        self.depth_reached = 0;
        self.best_score = 0;

        for depth in 1..=self.limits.depth.max(1) {
            let pv_move = best_move;
            root_moves.sort_by_key(|&m| -self.order_score(b, m, 0, pv_move));
            let mut alpha = -INFINITY;
            let mut iteration_best: Option<(i32, Move)> = None;

            for &m in root_moves.iter() {
                let next = b.make_move(m);
                let score = -self.negamax(&next, depth - 1, -INFINITY, -alpha, 1);
                if self.stopped {
                    break;
                }
                if score > alpha {
                    alpha = score;
                    iteration_best = Some((score, m));
                }
            }

            if self.stopped {
                // The previous best move is searched first, so a partial iteration's best is at least as informed
                if let Some((score, m)) = iteration_best {
                    self.best_score = score;
                    best_move = m;
                }
                break;
            }

            let (score, m) = iteration_best.unwrap();
            best_move = m;
            self.best_score = score;
            self.depth_reached = depth;
            self.tt_store(b.hash, depth, TT_EXACT, score, m, 0);
            let pv = self.principal_variation(b, m, depth as usize);
            on_info(&Info { depth, score, nodes: self.nodes, elapsed: self.start.elapsed(), pv: &pv });

            if score.abs() >= MATE_BOUND {
                break; // Forced mate found, deeper search won't change it
            }
            if let Some(limit) = self.limits.time {
                if self.start.elapsed() > limit / 2 {
                    break; // Next iteration would very likely not finish
                }
            }
        }
        best_move
    }

    /// Expected line of play: the best move, then each following position's hash move
    pub fn principal_variation(&self, b: &Board, best: Move, max_len: usize) -> Vec<Move> {
        let mut pv = vec![best];
        let mut pos = b.make_move(best);
        while pv.len() < max_len {
            let Some(entry) = self.tt_probe(pos.hash) else { break };
            if !legal_moves(&pos).contains(&entry.mv) {
                break;
            }
            pv.push(entry.mv);
            pos = pos.make_move(entry.mv);
        }
        pv
    }

    fn negamax(&mut self, b: &Board, depth: i32, mut alpha: i32, beta: i32, ply: usize) -> i32 {
        if self.should_stop() {
            return 0;
        }
        self.nodes += 1;
        let alpha_original = alpha;

        // A stored result at least this deep answers the node outright if it's exact or the bound is decisive
        let mut hash_move = NO_MOVE;
        if let Some(entry) = self.tt_probe(b.hash) {
            hash_move = entry.mv;
            if entry.depth as i32 >= depth {
                let score = score_from_tt(entry.score, ply);
                if entry.flag == TT_EXACT
                    || (entry.flag == TT_LOWER && score >= beta)
                    || (entry.flag == TT_UPPER && score <= alpha)
                {
                    return score;
                }
            }
        }

        let mut list = MoveList::new();
        generate(b, &mut list, false);

        if depth == 0 {
            if !list.iter().any(|m| !b.make_move(m).mover_in_check()) {
                return if b.in_check() { -(CHECKMATE - ply as i32) } else { 0 };
            }
            return self.quiescence(b, alpha, beta, ply);
        }

        let mut scores = [0i64; 256];
        for i in 0..list.len {
            scores[i] = self.order_score(b, list.moves[i], ply, hash_move);
        }

        let mut best_score = -INFINITY;
        let mut best_move = NO_MOVE;
        let mut legal = 0;
        for i in 0..list.len {
            pick_next(&mut list, &mut scores, i);
            let m = list.moves[i];
            let next = b.make_move(m);
            if next.mover_in_check() {
                continue;
            }
            legal += 1;

            let score = -self.negamax(&next, depth - 1, -beta, -alpha, ply + 1);
            if self.stopped {
                return 0;
            }
            if score > best_score {
                best_score = score;
                best_move = m;
            }
            if score > alpha {
                alpha = score;
            }
            if alpha >= beta {
                if is_quiet(m) {
                    self.store_killer(m, ply);
                    self.history[from_sq(m)][to_sq(m)] += (depth * depth) as i64;
                }
                break;
            }
        }

        if legal == 0 {
            return if b.in_check() { -(CHECKMATE - ply as i32) } else { 0 };
        }

        let flag = if best_score <= alpha_original {
            TT_UPPER
        } else if best_score >= beta {
            TT_LOWER
        } else {
            TT_EXACT
        };
        self.tt_store(b.hash, depth, flag, best_score, best_move, ply);
        best_score
    }

    // Only search captures and promotions past the horizon so the eval isn't taken mid-exchange
    fn quiescence(&mut self, b: &Board, mut alpha: i32, beta: i32, ply: usize) -> i32 {
        if self.should_stop() {
            return 0;
        }
        self.nodes += 1;

        let stand_pat = evaluate(b); // Side to move can usually decline to capture
        if stand_pat >= beta || ply >= MAX_PLY - 1 {
            return stand_pat;
        }
        if stand_pat > alpha {
            alpha = stand_pat;
        }

        let mut list = MoveList::new();
        generate(b, &mut list, true);
        let mut scores = [0i64; 256];
        for i in 0..list.len {
            scores[i] = mvv_lva(b, list.moves[i]) as i64;
        }

        for i in 0..list.len {
            pick_next(&mut list, &mut scores, i);
            let m = list.moves[i];
            let next = b.make_move(m);
            if next.mover_in_check() {
                continue;
            }
            let score = -self.quiescence(&next, -beta, -alpha, ply + 1);
            if self.stopped {
                return 0;
            }
            if score >= beta {
                return score;
            }
            if score > alpha {
                alpha = score;
            }
        }
        alpha
    }

    fn order_score(&self, b: &Board, m: Move, ply: usize, hash_move: Move) -> i64 {
        if m == hash_move {
            return PV_MOVE_SCORE;
        }
        if !is_quiet(m) {
            return CAPTURE_SCORE + mvv_lva(b, m) as i64;
        }
        let killers = &self.killers[ply];
        if killers[0] == m {
            return KILLER_SCORES[0];
        }
        if killers[1] == m {
            return KILLER_SCORES[1];
        }
        self.history[from_sq(m)][to_sq(m)]
    }

    fn store_killer(&mut self, m: Move, ply: usize) {
        let killers = &mut self.killers[ply];
        if killers[0] != m {
            killers[1] = killers[0];
            killers[0] = m;
        }
    }
}

/// Selection sort step: swap the best-scored remaining move into slot i
#[inline]
fn pick_next(list: &mut MoveList, scores: &mut [i64; 256], i: usize) {
    let mut best = i;
    for j in i + 1..list.len {
        if scores[j] > scores[best] {
            best = j;
        }
    }
    list.moves.swap(i, best);
    scores.swap(i, best);
}

fn mvv_lva(b: &Board, m: Move) -> i32 {
    let victim = if flag(m) == EN_PASSANT {
        MVV_LVA_VALUE[PAWN]
    } else if is_capture(m) {
        MVV_LVA_VALUE[b.mailbox[to_sq(m)] as usize % 6]
    } else {
        0
    };
    let promotion = if is_promotion(m) { MVV_LVA_VALUE[promotion_piece(m)] } else { 0 };
    (victim + promotion) * 10 - MVV_LVA_VALUE[b.mailbox[from_sq(m)] as usize % 6]
}

// Mate scores are stored relative to the node, not the root, so they stay correct when reached at another ply
fn score_to_tt(score: i32, ply: usize) -> i32 {
    if score >= MATE_BOUND {
        score + ply as i32
    } else if score <= -MATE_BOUND {
        score - ply as i32
    } else {
        score
    }
}

fn score_from_tt(score: i32, ply: usize) -> i32 {
    if score >= MATE_BOUND {
        score - ply as i32
    } else if score <= -MATE_BOUND {
        score + ply as i32
    } else {
        score
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn best(fen: &str, depth: i32) -> String {
        let mut s = Searcher::new(Arc::new(AtomicBool::new(false)));
        let limits = Limits { depth, ..Limits::default() };
        to_uci(s.search(&Board::from_fen(fen).unwrap(), limits, &mut |_| {}))
    }

    #[test]
    fn mate_in_one_white() {
        assert_eq!(best("6k1/5ppp/8/8/8/8/8/R5K1 w - - 0 1", 4), "a1a8");
    }

    #[test]
    fn mate_in_one_black() {
        assert_eq!(best("r5k1/8/8/8/8/8/5PPP/6K1 b - - 0 1", 4), "a8a1");
    }

    #[test]
    fn mate_in_two() {
        let m = best("7k/8/8/8/8/8/R7/1R4K1 w - - 0 1", 6);
        assert!(m == "a2a7" || m == "b1b7", "{m}");
    }

    #[test]
    fn mate_score_reported() {
        let mut s = Searcher::new(Arc::new(AtomicBool::new(false)));
        s.search(&Board::from_fen("6k1/5ppp/8/8/8/8/8/R5K1 w - - 0 1").unwrap(), Limits { depth: 4, ..Limits::default() }, &mut |_| {});
        assert_eq!(s.best_score, CHECKMATE - 1);
    }

    #[test]
    fn no_moves_returns_null() {
        assert_eq!(best("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1", 3), "0000"); // Stalemate
    }
}
