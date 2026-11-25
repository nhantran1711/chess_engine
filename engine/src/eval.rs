//! Tapered piece-square evaluation, ported from the earlier ChessGame/Evaluation.py (commit
//! d651436) with its hand-written Simplified Evaluation Function weights. The current Python
//! evaluation adds positional terms and Texel-tuned weights that are not ported yet.
//!
//! The tables below are written as in the Python file: White's point of view, rank 8 first.
//! For a board square (a1 = 0) a white piece reads entry `sq ^ 56` and a black piece reads
//! entry `sq`, which is the mirror image.

use crate::board::*;

// Indexed by piece type: pawn, knight, bishop, rook, queen, king.
// The king has no material value: it can never be traded, so it would only offset both sides equally.
const MG_VALUE: [i32; 6] = [100, 320, 330, 500, 900, 0];
const EG_VALUE: [i32; 6] = [100, 320, 330, 500, 900, 0];
/// How much each piece counts towards "middlegame-ness"; all pieces on the board sum to MAX_PHASE
const PHASE: [i32; 6] = [0, 1, 1, 2, 4, 0];
const MAX_PHASE: i32 = 24;

#[rustfmt::skip]
const PAWN_TABLE: [i32; 64] = [
      0,   0,   0,   0,   0,   0,   0,   0,
     50,  50,  50,  50,  50,  50,  50,  50,
     10,  10,  20,  30,  30,  20,  10,  10,
      5,   5,  10,  25,  25,  10,   5,   5,
      0,   0,   0,  20,  20,   0,   0,   0,
      5,  -5, -10,   0,   0, -10,  -5,   5,
      5,  10,  10, -20, -20,  10,  10,   5,
      0,   0,   0,   0,   0,   0,   0,   0,
];
#[rustfmt::skip]
const KNIGHT_TABLE: [i32; 64] = [
    -50, -40, -30, -30, -30, -30, -40, -50,
    -40, -20,   0,   0,   0,   0, -20, -40,
    -30,   0,  10,  15,  15,  10,   0, -30,
    -30,   5,  15,  20,  20,  15,   5, -30,
    -30,   0,  15,  20,  20,  15,   0, -30,
    -30,   5,  10,  15,  15,  10,   5, -30,
    -40, -20,   0,   5,   5,   0, -20, -40,
    -50, -40, -30, -30, -30, -30, -40, -50,
];
#[rustfmt::skip]
const BISHOP_TABLE: [i32; 64] = [
    -20, -10, -10, -10, -10, -10, -10, -20,
    -10,   0,   0,   0,   0,   0,   0, -10,
    -10,   0,   5,  10,  10,   5,   0, -10,
    -10,   5,   5,  10,  10,   5,   5, -10,
    -10,   0,  10,  10,  10,  10,   0, -10,
    -10,  10,  10,  10,  10,  10,  10, -10,
    -10,   5,   0,   0,   0,   0,   5, -10,
    -20, -10, -10, -10, -10, -10, -10, -20,
];
#[rustfmt::skip]
const ROOK_TABLE: [i32; 64] = [
      0,   0,   0,   0,   0,   0,   0,   0,
      5,  10,  10,  10,  10,  10,  10,   5,
     -5,   0,   0,   0,   0,   0,   0,  -5,
     -5,   0,   0,   0,   0,   0,   0,  -5,
     -5,   0,   0,   0,   0,   0,   0,  -5,
     -5,   0,   0,   0,   0,   0,   0,  -5,
     -5,   0,   0,   0,   0,   0,   0,  -5,
      0,   0,   0,   5,   5,   0,   0,   0,
];
#[rustfmt::skip]
const QUEEN_TABLE: [i32; 64] = [
    -20, -10, -10,  -5,  -5, -10, -10, -20,
    -10,   0,   0,   0,   0,   0,   0, -10,
    -10,   0,   5,   5,   5,   5,   0, -10,
     -5,   0,   5,   5,   5,   5,   0,  -5,
      0,   0,   5,   5,   5,   5,   0,  -5,
    -10,   5,   5,   5,   5,   5,   0, -10,
    -10,   0,   5,   0,   0,   0,   0, -10,
    -20, -10, -10,  -5,  -5, -10, -10, -20,
];
#[rustfmt::skip]
const KING_MG_TABLE: [i32; 64] = [
    -30, -40, -40, -50, -50, -40, -40, -30,
    -30, -40, -40, -50, -50, -40, -40, -30,
    -30, -40, -40, -50, -50, -40, -40, -30,
    -30, -40, -40, -50, -50, -40, -40, -30,
    -20, -30, -30, -40, -40, -30, -30, -20,
    -10, -20, -20, -20, -20, -20, -20, -10,
     20,  20,   0,   0,   0,   0,  20,  20,
     20,  30,  10,   0,   0,  10,  30,  20,
];
#[rustfmt::skip]
const KING_EG_TABLE: [i32; 64] = [
    -50, -40, -30, -20, -20, -30, -40, -50,
    -30, -20, -10,   0,   0, -10, -20, -30,
    -30, -10,  20,  30,  30,  20, -10, -30,
    -30, -10,  30,  40,  40,  30, -10, -30,
    -30, -10,  30,  40,  40,  30, -10, -30,
    -30, -10,  20,  30,  30,  20, -10, -30,
    -30, -30,   0,   0,   0,   0, -30, -30,
    -50, -30, -30, -30, -30, -30, -30, -50,
];

// Only the king's table differs between midgame and endgame, as in EvalParams.py
const MG_TABLES: [[i32; 64]; 6] = [PAWN_TABLE, KNIGHT_TABLE, BISHOP_TABLE, ROOK_TABLE, QUEEN_TABLE, KING_MG_TABLE];
const EG_TABLES: [[i32; 64]; 6] = [PAWN_TABLE, KNIGHT_TABLE, BISHOP_TABLE, ROOK_TABLE, QUEEN_TABLE, KING_EG_TABLE];

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

static MG: [[i32; 64]; 12] = square_scores(MG_VALUE, MG_TABLES);
static EG: [[i32; 64]; 12] = square_scores(EG_VALUE, EG_TABLES);

/// Centipawns from White's point of view. Positive means White is better.
pub fn evaluate_white(b: &Board) -> i32 {
    let (mut mg, mut eg, mut phase) = (0, 0, 0);
    for color in [WHITE, BLACK] {
        for piece in PAWN..=KING {
            let code = color * 6 + piece;
            let mut bb = b.pieces[piece] & b.colors[color];
            phase += PHASE[piece] * bb.count_ones() as i32;
            while bb != 0 {
                let sq = crate::attacks::pop_lsb(&mut bb);
                mg += MG[code][sq];
                eg += EG[code][sq];
            }
        }
    }
    let phase = phase.min(MAX_PHASE); // Early promotions can push it past the starting total
    // Floor division, as Python's // does. Rust's `/` truncates towards zero, which would make
    // negative scores differ by 1 from the Python engine and break the cross-check against it.
    (mg * phase + eg * (MAX_PHASE - phase)).div_euclid(MAX_PHASE)
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
