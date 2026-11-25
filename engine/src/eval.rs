//! Tapered evaluation, the same as ChessGame/Evaluation.py, with the Texel-tuned weights from
//! ChessGame/EvalParams.py (exported to params.rs by tuning/export_rust_params.py).
//!
//! Two parts, each scored with midgame and endgame weights:
//!   - piece-square: every piece scores its material value plus a bonus for its square
//!   - positional terms: passed, doubled and isolated pawns, the pawn shield and open files
//!     around the king, the bishop pair, and rooks on open or half-open files
//!
//! The two are blended by game phase (knight/bishop 1, rook 2, queen 4, 24 at the start):
//!
//! ```text
//! score = (mg * phase + eg * (24 - phase)) / 24
//! ```
//!
//! Tables in params.rs are written White's point of view, rank 8 first. For a board square
//! (a1 = 0) a white piece reads entry `sq ^ 56` and a black piece reads entry `sq`, its mirror image.

use crate::attacks::{bit, pop_lsb};
use crate::board::*;
use crate::params::*;

/// How much each piece counts towards "middlegame-ness"; all pieces on the board sum to MAX_PHASE
const PHASE: [i32; 6] = [0, 1, 1, 2, 4, 0];
const MAX_PHASE: i32 = 24;

// Indexes into TERM_MG / TERM_EG, in the order of termNames in EvalParams.py.
// A passed pawn on its own rank k (2..=7) uses PASSED + k - 2.
const PASSED: usize = 0;
const DOUBLED: usize = 6;
const ISOLATED: usize = 7;
const SHIELD1: usize = 8;
const SHIELD2: usize = 9;
const KING_OPEN_FILE: usize = 10;
const BISHOP_PAIR: usize = 11;
const ROOK_OPEN: usize = 12;
const ROOK_HALF_OPEN: usize = 13;
const NUM_TERMS: usize = 14;

const FILE_A: u64 = 0x0101_0101_0101_0101;

/// Material + square bonus for every (piece code, square), with Black's negated, so the
/// evaluation loop is a plain sum with no colour branches.
const fn square_scores(values: [i32; 6], tables: [[i32; 64]; 6]) -> [[i32; 64]; 12] {
    let mut scores = [[0; 64]; 12];
    let mut piece = 0;
    while piece < 6 {
        let mut sq = 0;
        while sq < 64 {
            scores[piece][sq] = values[piece] + tables[piece][sq ^ 56];
            scores[6 + piece][sq] = -(values[piece] + tables[piece][sq]);
            sq += 1;
        }
        piece += 1;
    }
    scores
}

static MG: [[i32; 64]; 12] = square_scores(MG_VALUE, MG_TABLE);
static EG: [[i32; 64]; 12] = square_scores(EG_VALUE, EG_TABLE);

/// `PASSED_MASK[colour][sq]`: squares ahead of a pawn on its own and adjacent files. The pawn is
/// passed when no enemy pawn stands on any of them.
static PASSED_MASK: [[u64; 64]; 2] = {
    let mut masks = [[0u64; 64]; 2];
    let mut sq = 0;
    while sq < 64 {
        let file = sq % 8;
        let rank = sq / 8;
        let mut f = if file > 0 { file - 1 } else { 0 };
        while f <= file + 1 && f < 8 {
            let mut r = 0;
            while r < 8 {
                if r > rank {
                    masks[WHITE][sq] |= 1u64 << (r * 8 + f);
                }
                if r < rank {
                    masks[BLACK][sq] |= 1u64 << (r * 8 + f);
                }
                r += 1;
            }
            f += 1;
        }
        sq += 1;
    }
    masks
};

/// Centipawns from White's point of view. Positive means White is better.
pub fn evaluate_white(b: &Board) -> i32 {
    let (mut mg, mut eg, mut phase) = (0, 0, 0);
    for color in [WHITE, BLACK] {
        for piece in PAWN..=KING {
            let code = color * 6 + piece;
            let mut bb = b.pieces[piece] & b.colors[color];
            phase += PHASE[piece] * bb.count_ones() as i32;
            while bb != 0 {
                let sq = pop_lsb(&mut bb);
                mg += MG[code][sq];
                eg += EG[code][sq];
            }
        }
    }
    let counts = term_counts(b);
    for i in 0..NUM_TERMS {
        mg += counts[i] * TERM_MG[i];
        eg += counts[i] * TERM_EG[i];
    }
    let phase = phase.min(MAX_PHASE); // Early promotions can push it past the starting total
    // Rust's `/` rounds towards zero, as the Python version does on purpose, so a position and its
    // colour-mirror score exactly opposite
    (mg * phase + eg * (MAX_PHASE - phase)) / MAX_PHASE
}

/// Centipawns from the side to move's point of view, which is what negamax needs
#[inline]
pub fn evaluate(b: &Board) -> i32 {
    let score = evaluate_white(b);
    if b.side == WHITE {
        score
    } else {
        -score
    }
}

/// Count of each positional term, White's minus Black's (Evaluation.evalTerms in Python)
fn term_counts(b: &Board) -> [i32; NUM_TERMS] {
    let mut counts = [0i32; NUM_TERMS];
    for color in [WHITE, BLACK] {
        let sign = if color == WHITE { 1 } else { -1 };
        let own_pawns = b.pieces[PAWN] & b.colors[color];
        let enemy_pawns = b.pieces[PAWN] & b.colors[color ^ 1];
        let file_has = |pawns: u64, f: usize| pawns & (FILE_A << f) != 0;

        for f in 0..8 {
            let on_file = (own_pawns & (FILE_A << f)).count_ones() as i32;
            if on_file == 0 {
                continue;
            }
            if on_file > 1 {
                counts[DOUBLED] += sign * (on_file - 1);
            }
            let left = f > 0 && file_has(own_pawns, f - 1);
            let right = f < 7 && file_has(own_pawns, f + 1);
            if !left && !right {
                counts[ISOLATED] += sign * on_file;
            }
        }

        let mut pawns = own_pawns;
        while pawns != 0 {
            let sq = pop_lsb(&mut pawns);
            if PASSED_MASK[color][sq] & enemy_pawns == 0 {
                // The pawn's rank counted from its own side, 2..=7
                let rank = if color == WHITE { sq / 8 + 1 } else { 8 - sq / 8 };
                counts[PASSED + rank - 2] += sign;
            }
        }

        // Pawn shield: own pawns one or two ranks in front of the king, on its file and the two beside it
        let king = b.king_square(color);
        let (kf, kr) = ((king % 8) as i32, (king / 8) as i32);
        let ahead = if color == WHITE { 1 } else { -1 };
        for f in kf - 1..=kf + 1 {
            if !(0..8).contains(&f) {
                continue;
            }
            let at = |r: i32| (0..8).contains(&r) && own_pawns & bit((r * 8 + f) as usize) != 0;
            if at(kr + ahead) {
                counts[SHIELD1] += sign;
            } else if at(kr + 2 * ahead) {
                counts[SHIELD2] += sign;
            }
            if !file_has(own_pawns, f as usize) {
                counts[KING_OPEN_FILE] += sign;
            }
        }

        if (b.pieces[BISHOP] & b.colors[color]).count_ones() >= 2 {
            counts[BISHOP_PAIR] += sign;
        }
        let mut rooks = b.pieces[ROOK] & b.colors[color];
        while rooks != 0 {
            let f = pop_lsb(&mut rooks) % 8;
            if !file_has(own_pawns, f) {
                counts[if file_has(enemy_pawns, f) { ROOK_HALF_OPEN } else { ROOK_OPEN }] += sign;
            }
        }
    }
    counts
}
