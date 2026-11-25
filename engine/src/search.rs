//! Alpha-beta (negamax) search, ported from `Searcher` in ChessGame/ChessAI.py:
//!
//! - iterative deepening with aspiration windows, principal variation search (PVS)
//! - transposition table, quiescence search with SEE pruning
//! - draw detection: repetitions and the fifty-move rule
//! - check extension, null-move pruning, futility pruning, late move reductions (LMR)
//! - move ordering: hash move, captures by MVV-LVA + capture history (losing captures by SEE
//!   after the killers), killer moves, quiet moves by history + continuation history
//!
//! Scores are relative to the side to move. Mate is CHECKMATE - ply, so faster mates score higher.
//!
//! Stopping: when a limit is hit, `stopped` is set and every node returns 0 immediately. That 0
//! is meaningless, so every caller checks `self.stopped` right after a recursive call and
//! returns before using the score, storing it in the table, or updating killers/history.

use crate::board::*;
use crate::eval::evaluate;
use crate::movegen::*;
use crate::moves::*;
use crate::see::see;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};

pub const CHECKMATE: i32 = 100_000;
pub const MAX_PLY: usize = 128;
pub const MAX_DEPTH: i32 = 64;
/// Any score at least this far from 0 is a mate score, since no mate is deeper than MAX_PLY
pub const MATE_BOUND: i32 = CHECKMATE - MAX_PLY as i32;
/// Beyond any real score, so the window (-INFINITY, INFINITY) never cuts anything off
const INFINITY: i32 = CHECKMATE + 1;

// Move ordering bands, far enough apart that each category always sorts above the next:
// hash move > winning/equal captures > killers > losing captures (by SEE) > quiet moves
const PV_MOVE_SCORE: i64 = 1 << 50;
const GOOD_CAPTURE_SCORE: i64 = 1 << 46;
const KILLER_SCORES: [i64; 2] = [(1 << 45) + 1, 1 << 45];
const BAD_CAPTURE_SCORE: i64 = 1 << 44;
// Ordering values, separate from evaluation so the king counts as the most valuable attacker
const MVV_LVA_VALUE: [i32; 6] = [1, 3, 3, 5, 9, 10];

/// Bound for the capture and continuation history tables (see `update_history`)
const HISTORY_MAX: i32 = 16384;
const CAPTURE_HISTORY_SIZE: usize = 12 * 64 * 6; // [piece moved][to][victim type]
const CONT_HISTORY_SIZE: usize = 12 * 64 * 12 * 64; // [previous piece][its to][piece][to]

const ASPIRATION_WINDOW: i32 = 50; // Centipawns either side of the previous depth's score
const FUTILITY_MARGIN: [i32; 3] = [0, 200, 450]; // By remaining depth: what a quiet move could plausibly gain

/// 2^20 entries of 24 bytes = 24 MB. Must stay a power of two: entries are indexed by `hash & (len - 1)`.
const TT_SIZE_BITS: usize = 20;
const TT_EXACT: u8 = 0;
const TT_LOWER: u8 = 1; // score >= stored (beta cutoff)
const TT_UPPER: u8 = 2; // score <= stored (failed low)

#[derive(Clone, Copy, Default)]
struct TTEntry {
    /// Full hash, so a probe can tell its own position from another one sharing the slot
    key: u64,
    /// Mate scores stored relative to this node (see `score_to_tt`)
    score: i32,
    /// Best move found, tried first next time even when the score can't be used
    mv: Move,
    /// Remaining depth the score was searched to
    depth: i8,
    /// TT_EXACT, TT_LOWER or TT_UPPER
    flag: u8,
    /// Search that wrote it; entries from older searches are always replaceable
    age: u8,
}

/// When to stop searching. `None` means no limit of that kind.
#[derive(Clone, Copy, Debug)]
pub struct Limits {
    /// Hard deadline; the search also won't start a new depth after half of it
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
    history: Vec<[i64; 64]>, // [from][to], reset every search
    // Learned ordering tables, kept between moves of a game (bounded by history gravity)
    capture_history: Vec<i32>,
    cont_history: Vec<i32>,
    /// Hashes of every position before the current node: the game so far, then the search path.
    /// Used for repetition detection
    keys: Vec<u64>,
    pub nodes: u64,
    pub depth_reached: i32,
    pub best_score: i32,
    has_score: bool,
    /// Best root move of the iteration in progress, used if the search stops partway through it
    partial: Option<(i32, Move)>,
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
            capture_history: vec![0; CAPTURE_HISTORY_SIZE],
            cont_history: vec![0; CONT_HISTORY_SIZE],
            keys: Vec::with_capacity(1024),
            nodes: 0,
            depth_reached: 0,
            best_score: 0,
            has_score: false,
            partial: None,
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
            let depth = depth.clamp(i8::MIN as i32, i8::MAX as i32) as i8;
            self.tt[index] = TTEntry { key, score: score_to_tt(score, ply), mv, depth, flag, age: self.tt_age };
        }
    }

    /// Checks the limits. Reading the clock and the shared atomic is slow next to a node, so
    /// those are only checked every 1024 nodes, well under a millisecond.
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

    /// Fifty-move rule, or the position already occurred since the last capture or pawn move.
    /// A single repetition counts: if repeating was good once, the same reasoning repeats it again.
    /// Only positions with the same side to move can match, hence every second entry.
    fn is_draw(&self, b: &Board) -> bool {
        if b.halfmove >= 100 {
            return true;
        }
        let n = self.keys.len();
        let lookback = (b.halfmove as usize).min(n);
        (2..=lookback).step_by(2).any(|i| self.keys[n - i] == b.hash)
    }

    fn next_random(&mut self) -> u64 {
        self.rng ^= self.rng << 13;
        self.rng ^= self.rng >> 7;
        self.rng ^= self.rng << 17;
        self.rng
    }

    /// Iterative deepening: search depth 1, 2, 3, ... until a limit is hit, keep the last completed
    /// result. `game_history` holds the hashes of the positions before `b` in the game, for
    /// repetition detection. Returns NO_MOVE when there are no legal moves.
    pub fn search(&mut self, b: &Board, game_history: &[u64], limits: Limits, on_info: &mut dyn FnMut(&Info)) -> Move {
        self.reset_tables();
        self.tt_age = self.tt_age.wrapping_add(1);
        self.start = Instant::now();
        self.limits = limits;
        self.keys.clear();
        self.keys.extend_from_slice(game_history);

        let mut root_moves = legal_moves(b);
        if root_moves.is_empty() {
            return NO_MOVE;
        }
        for i in (1..root_moves.len()).rev() {
            // Variety between equally scored moves
            let j = (self.next_random() % (i as u64 + 1)) as usize;
            root_moves.swap(i, j);
        }

        root_moves.sort_by_key(|&m| -self.order_score(b, m, 0, NO_MOVE, None, false));
        // Fallback if not even one root move finishes: best capture by MVV-LVA
        let mut best_move = root_moves[0];
        if let Some(entry) = self.tt_probe(b.hash) {
            if root_moves.contains(&entry.mv) {
                best_move = entry.mv;
            }
        }
        self.depth_reached = 0;
        self.best_score = 0;
        self.has_score = false;
        self.partial = None;

        for depth in 1..=self.limits.depth.max(1) {
            let (score, m) = self.search_depth(b, &mut root_moves, depth, best_move);
            if self.stopped {
                // The previous best move is searched first, so a partial iteration's best is at least as informed
                if let Some((score, m)) = self.partial {
                    self.best_score = score;
                    best_move = m;
                }
                break;
            }

            best_move = m;
            self.best_score = score;
            self.has_score = true;
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

    /// Aspiration windows: the score rarely moves far between depths, so search a narrow window
    /// around the last one, which cuts off more. If the true score lands outside it, widen and repeat.
    fn search_depth(&mut self, b: &Board, root_moves: &mut [Move], depth: i32, mut pv_move: Move) -> (i32, Move) {
        if depth < 4 || !self.has_score || self.best_score.abs() >= MATE_BOUND {
            return self.search_root(b, root_moves, depth, pv_move, -INFINITY, INFINITY);
        }
        let mut window = ASPIRATION_WINDOW;
        let (mut alpha, mut beta) = (self.best_score - window, self.best_score + window);
        loop {
            let (score, m) = self.search_root(b, root_moves, depth, pv_move, alpha, beta);
            if self.stopped || (alpha < score && score < beta) || (alpha == -INFINITY && beta == INFINITY) {
                return (score, m);
            }
            window *= 4;
            if window > 1000 {
                (alpha, beta) = (-INFINITY, INFINITY);
            } else if score <= alpha {
                alpha = score - window; // Failed low: every move is worse than expected
            } else {
                beta = score + window; // Failed high: this move is better than expected, so it goes first next time
                pv_move = m;
            }
        }
    }

    /// Returns (score, move). A score <= alpha or >= beta is only a bound: the window was missed.
    fn search_root(&mut self, b: &Board, root_moves: &mut [Move], depth: i32, pv_move: Move, mut alpha: i32, beta: i32) -> (i32, Move) {
        root_moves.sort_by_key(|&m| -self.order_score(b, m, 0, pv_move, None, false));
        let alpha_original = alpha;
        let mut best_move = root_moves[0];
        self.partial = None;

        self.keys.push(b.hash);
        for (i, &m) in root_moves.iter().enumerate() {
            let next = b.make_move(m);
            let mut score;
            if i == 0 {
                score = -self.negamax(&next, depth - 1, -beta, -alpha, 1, m);
            } else {
                // Principal variation search: prove the move is no better with a zero window, re-search if it is
                score = -self.negamax(&next, depth - 1, -alpha - 1, -alpha, 1, m);
                if score > alpha && !self.stopped {
                    score = -self.negamax(&next, depth - 1, -beta, -alpha, 1, m);
                }
            }
            if self.stopped {
                break;
            }
            if score > alpha {
                alpha = score;
                best_move = m;
                self.partial = Some((score, m));
                if alpha >= beta {
                    break;
                }
            }
        }
        self.keys.pop();

        if alpha == alpha_original {
            best_move = pv_move; // Failed low, no move was any good: keep the previous best for ordering
        }
        (alpha, best_move)
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

    /// Searches a child: pushes this node's hash for repetition detection, then pops it.
    /// Returns the child's score from the child's point of view (the caller negates it).
    #[inline]
    fn child(&mut self, parent: &Board, next: &Board, depth: i32, alpha: i32, beta: i32, ply: usize, m: Move) -> i32 {
        self.keys.push(parent.hash);
        let score = self.negamax(next, depth, alpha, beta, ply, m);
        self.keys.pop();
        score
    }

    /// Score of `b` for the side to move, searched `depth` plies deep.
    ///
    /// `alpha`/`beta` is the window: a result <= alpha means "this line is worse than one we
    /// already have" (an upper bound), >= beta means "the opponent won't allow this" (a lower
    /// bound). Fail-soft: the returned score may lie outside the window, which gives tighter
    /// bounds to store. `ply` is the distance from the root, for mate scores and killers.
    /// `prev` is the move that led here (NO_MOVE after a null move), for continuation history.
    fn negamax(&mut self, b: &Board, depth: i32, mut alpha: i32, beta: i32, ply: usize, prev: Move) -> i32 {
        if self.should_stop() {
            return 0;
        }
        self.nodes += 1;
        if self.is_draw(b) {
            return 0; // Always ply >= 1 here: the root's moves are searched from search_root
        }
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

        let in_check = b.in_check();
        let mut depth = depth;
        if in_check && ply < MAX_PLY / 2 {
            depth += 1; // Check extension: a check forces a reply, so it shouldn't use up the depth
        }

        // Leaf not in check: straight to quiescence, which only generates captures. Generating
        // every move here would only detect stalemate, and leaves are about half of all nodes
        if depth <= 0 && !in_check {
            return self.quiescence(b, alpha, beta, ply);
        }

        let mut list = MoveList::new();
        generate(b, &mut list, false);

        if depth <= 0 {
            // In check at the horizon: mated if there's no way out, otherwise resolve captures
            if !list.iter().any(|m| !b.make_move(m).mover_in_check()) {
                return -(CHECKMATE - ply as i32);
            }
            return self.quiescence(b, alpha, beta, ply);
        }

        let is_pv = beta - alpha > 1; // Zero-window nodes only ask "better than alpha or not?"
        let static_eval = if is_pv || in_check { 0 } else { evaluate(b) };

        // Null-move pruning: let the opponent move twice. If we still reach beta, a real move would too.
        // Unsafe in zugzwang, which is mostly king-and-pawn endings, so those are excluded
        if !is_pv && !in_check && depth >= 3 && ply < MAX_PLY - 10 && b.has_pieces() && static_eval >= beta {
            let reduction = if depth >= 6 { 3 } else { 2 };
            let next = b.make_null_move();
            let score = -self.child(b, &next, depth - 1 - reduction, -beta, -beta + 1, ply + 1, NO_MOVE);
            if self.stopped {
                return 0;
            }
            if score >= beta {
                return if score >= MATE_BOUND { beta } else { score }; // Don't trust a mate found by passing
            }
        }

        // Futility pruning: one or two plies from the horizon, if even a generous margin on top of
        // the static evaluation can't reach alpha, quiet moves won't either. Captures, promotions and
        // checks can swing the score more, so they're still searched; so is the first move
        let futile = !is_pv
            && !in_check
            && (depth as usize) < FUTILITY_MARGIN.len()
            && alpha.abs() < MATE_BOUND
            && static_eval + FUTILITY_MARGIN[depth as usize] <= alpha;

        let prev_key = cont_key(b, prev);
        // Score every move once, then pick the best remaining one lazily: after a beta cutoff,
        // which usually comes in the first few moves, the rest never need sorting
        let mut scores = [0i64; 256];
        for i in 0..list.len {
            scores[i] = self.order_score(b, list.moves[i], ply, hash_move, prev_key, true);
        }

        let mut best_score = -INFINITY;
        let mut best_move = NO_MOVE;
        let mut legal = 0;
        // Moves searched without causing a cutoff, penalised in the history tables when a later one does
        let mut tried_quiets = [NO_MOVE; 64];
        let mut tried_captures = [NO_MOVE; 32];
        let (mut n_quiets, mut n_captures) = (0, 0);

        for i in 0..list.len {
            pick_next(&mut list, &mut scores, i);
            let m = list.moves[i];
            let next = b.make_move(m);
            if next.mover_in_check() {
                continue;
            }
            let index = legal; // Position among the legal moves, in search order
            legal += 1;

            // The check test is the costly part, so only run it when futility or LMR could use it
            let may_prune = futile || (depth >= 3 && index >= 3 && !in_check);
            let quiet_no_check = may_prune && index > 0 && is_quiet(m) && !next.in_check();
            if futile && quiet_no_check {
                continue;
            }

            let mut score;
            if index == 0 {
                score = -self.child(b, &next, depth - 1, -beta, -alpha, ply + 1, m);
            } else {
                // Late move reductions: with good ordering, quiet moves this far down rarely matter,
                // so search them shallower first and only at full depth if they beat alpha
                let mut reduction = 0;
                if depth >= 3 && index >= 3 && !in_check && quiet_no_check {
                    reduction = if index >= 8 && depth >= 5 { 2 } else { 1 };
                }
                score = -self.child(b, &next, depth - 1 - reduction, -alpha - 1, -alpha, ply + 1, m);
                if score > alpha && reduction > 0 && !self.stopped {
                    score = -self.child(b, &next, depth - 1, -alpha - 1, -alpha, ply + 1, m);
                }
                if alpha < score && score < beta && !self.stopped {
                    // Principal variation search: re-search with the full window
                    score = -self.child(b, &next, depth - 1, -beta, -alpha, ply + 1, m);
                }
            }
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
                // Reward the move that refuted this line and penalise the ones tried before it:
                // they will likely refute sibling lines too
                let bonus = depth * depth;
                if is_quiet(m) {
                    self.store_killer(m, ply);
                    self.history[from_sq(m)][to_sq(m)] += bonus as i64;
                    if let Some(key) = prev_key {
                        update_history(&mut self.cont_history[key + piece_to(b, m)], bonus);
                        for &tried in &tried_quiets[..n_quiets] {
                            update_history(&mut self.cont_history[key + piece_to(b, tried)], -bonus);
                        }
                    }
                } else {
                    update_history(&mut self.capture_history[capture_key(b, m)], bonus);
                    for &tried in &tried_captures[..n_captures] {
                        update_history(&mut self.capture_history[capture_key(b, tried)], -bonus);
                    }
                }
                break;
            }
            if is_quiet(m) {
                if n_quiets < tried_quiets.len() {
                    tried_quiets[n_quiets] = m;
                    n_quiets += 1;
                }
            } else if n_captures < tried_captures.len() {
                tried_captures[n_captures] = m;
                n_captures += 1;
            }
        }

        if legal == 0 {
            return if in_check { -(CHECKMATE - ply as i32) } else { 0 };
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

        // "Stand pat": the side to move can usually decline every capture, so the static eval is
        // a lower bound on its score
        let stand_pat = evaluate(b);
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
            scores[i] = self.capture_order(b, list.moves[i]);
        }

        for i in 0..list.len {
            pick_next(&mut list, &mut scores, i);
            let m = list.moves[i];
            // SEE pruning: a capture that loses material once the recaptures are played out can't
            // raise alpha above the stand-pat score, so skip it
            if !is_promotion(m) && may_lose_material(b, m) && see(b, m) < 0 {
                continue;
            }
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

    /// MVV-LVA, with capture history breaking ties within one MVV-LVA step
    #[inline]
    fn capture_order(&self, b: &Board, m: Move) -> i64 {
        mvv_lva(b, m) as i64 * HISTORY_MAX as i64 + self.capture_history[capture_key(b, m)] as i64
    }

    /// Higher sorts first. `use_see` demotes captures that lose material below the killers
    /// (not at the root, where every move is searched anyway).
    fn order_score(&self, b: &Board, m: Move, ply: usize, hash_move: Move, prev_key: Option<usize>, use_see: bool) -> i64 {
        if m == hash_move {
            return PV_MOVE_SCORE;
        }
        if !is_quiet(m) {
            let score = self.capture_order(b, m);
            if use_see && !is_promotion(m) && may_lose_material(b, m) && see(b, m) < 0 {
                return BAD_CAPTURE_SCORE + score;
            }
            return GOOD_CAPTURE_SCORE + score;
        }
        let killers = &self.killers[ply];
        if killers[0] == m {
            return KILLER_SCORES[0];
        }
        if killers[1] == m {
            return KILLER_SCORES[1];
        }
        let mut score = self.history[from_sq(m)][to_sq(m)];
        if let Some(key) = prev_key {
            score += self.cont_history[key + piece_to(b, m)] as i64;
        }
        score
    }

    fn store_killer(&mut self, m: Move, ply: usize) {
        let killers = &mut self.killers[ply];
        if killers[0] != m {
            killers[1] = killers[0];
            killers[0] = m;
        }
    }
}

/// History gravity: move towards +/-HISTORY_MAX, slowing as it gets there, so old results fade
/// and the value can never overflow its band.
#[inline]
fn update_history(entry: &mut i32, bonus: i32) {
    let bonus = bonus.clamp(-HISTORY_MAX, HISTORY_MAX);
    *entry += bonus - *entry * bonus.abs() / HISTORY_MAX;
}

/// Index of the moved piece and its destination within one continuation-history block
#[inline]
fn piece_to(b: &Board, m: Move) -> usize {
    b.mailbox[from_sq(m)] as usize * 64 + to_sq(m)
}

/// Offset of the block for the move that led to `b`, or None after a null move / at the start.
/// The piece is read from its destination, so a promotion counts as the promoted piece.
#[inline]
fn cont_key(b: &Board, prev: Move) -> Option<usize> {
    if prev == NO_MOVE {
        return None;
    }
    let to = to_sq(prev);
    Some((b.mailbox[to] as usize * 64 + to) * 768)
}

/// Capture history index: piece moved, destination, type of the piece captured (pawn for a quiet promotion)
#[inline]
fn capture_key(b: &Board, m: Move) -> usize {
    let victim = if is_capture(m) && flag(m) != EN_PASSANT { b.mailbox[to_sq(m)] as usize % 6 } else { PAWN };
    (b.mailbox[from_sq(m)] as usize * 64 + to_sq(m)) * 6 + victim
}

/// Taking a piece worth at least the capturer can't lose material, so SEE is only needed otherwise
#[inline]
fn may_lose_material(b: &Board, m: Move) -> bool {
    is_capture(m)
        && flag(m) != EN_PASSANT
        && MVV_LVA_VALUE[b.mailbox[from_sq(m)] as usize % 6] > MVV_LVA_VALUE[b.mailbox[to_sq(m)] as usize % 6]
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

/// Most Valuable Victim, Least Valuable Attacker: PxQ before QxQ before QxP. The victim is
/// weighted 10x so it always dominates, and the attacker breaks ties.
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

// Mate scores are stored relative to the node, not the root, so they stay correct when reached at another ply.
// Example: "mate in 3 plies from this node" found at ply 5 is CHECKMATE - 8 at the root; stored as
// CHECKMATE - 3, it becomes CHECKMATE - 10 when the same position is reached again at ply 7.
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

    fn searcher() -> Searcher {
        Searcher::new(Arc::new(AtomicBool::new(false)))
    }

    fn best(fen: &str, depth: i32) -> String {
        let limits = Limits { depth, ..Limits::default() };
        to_uci(searcher().search(&Board::from_fen(fen).unwrap(), &[], limits, &mut |_| {}))
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
        let mut s = searcher();
        s.search(&Board::from_fen("6k1/5ppp/8/8/8/8/8/R5K1 w - - 0 1").unwrap(), &[], Limits { depth: 4, ..Limits::default() }, &mut |_| {});
        assert_eq!(s.best_score, CHECKMATE - 1);
    }

    #[test]
    fn no_moves_returns_null() {
        assert_eq!(best("7k/5Q2/6K1/8/8/8/8/8 b - - 0 1", 3), "0000"); // Stalemate
    }

    #[test]
    fn wins_material_with_a_fork() {
        // Nc7+ forks king and rook
        assert_eq!(best("r3k3/8/8/1N6/8/8/8/4K3 w - - 0 1", 6), "b5c7");
    }

    // Repetitions and the fifty-move rule are draws
    #[test]
    fn detects_draws() {
        let mut s = searcher();
        let mut b = Board::startpos();
        for uci in ["g1f3", "g8f6", "f3g1", "f6g8"] {
            s.keys.push(b.hash);
            let m = legal_moves(&b).into_iter().find(|&m| to_uci(m) == uci).unwrap();
            b = b.make_move(m);
        }
        assert!(s.is_draw(&b), "start position repeated");
        s.keys.clear();
        assert!(!s.is_draw(&b));
        assert!(s.is_draw(&Board::from_fen("4k3/8/8/8/8/8/8/R3K3 w - - 100 80").unwrap()));
    }
}
