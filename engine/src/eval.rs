//! Tapered evaluation with Texel-tuned weights (params.rs, written by `chessgame tune`).
//!
//! Two parts, each scored with midgame and endgame weights:
//!   - piece-square: every piece scores its material value plus a bonus for its square
//!   - positional terms (`term_counts`): pawn structure (passed, doubled, isolated, supported,
//!     phalanx; passed-pawn blockers and king distances), king safety (pawn shield, open files,
//!     attacks on the king zone, number of attackers, safe checks), mobility tables per piece,
//!     threats (pawn and minor attacks on bigger pieces, undefended pieces), outposts, the
//!     bishop pair, rooks on open files and the seventh rank, and a side-to-move bonus
//!
//! The two are blended by game phase (knight/bishop 1, rook 2, queen 4, 24 at the start):
//!
//! ```text
//! score = (mg * phase + eg * (24 - phase)) / 24
//! ```
//!
//! Tables in params.rs are written White's point of view, rank 8 first. For a board square
//! (a1 = 0) a white piece reads entry `sq ^ 56` and a black piece reads entry `sq`, its mirror image.

use crate::attacks::*;
use crate::board::*;
use crate::params::*;

/// How much each piece counts towards "middlegame-ness"; all pieces on the board sum to MAX_PHASE
pub const PHASE: [i32; 6] = [0, 1, 1, 2, 4, 0];
pub const MAX_PHASE: i32 = 24;

// Indexes into TERM_MG / TERM_EG. A passed pawn on its own rank k (2..=7) uses PASSED + k - 2.
const PASSED: usize = 0;
const DOUBLED: usize = 6;
const ISOLATED: usize = 7;
const SHIELD1: usize = 8;
const SHIELD2: usize = 9;
const KING_OPEN_FILE: usize = 10;
const BISHOP_PAIR: usize = 11;
const ROOK_OPEN: usize = 12;
const ROOK_HALF_OPEN: usize = 13;
/// Mobility tables: one weight per number of safe squares a piece attacks.
/// MOBILITY[p] is the first index for piece type p (knight..queen); its block has room for
/// 9, 14, 15 and 28 entries (0..=max squares), of which 0..=MOBILITY_CAP[p] are used
const MOBILITY: [usize; 6] = [0, 14, 23, 37, 52, 0];
/// Counts above this share one weight: a queen attacking 22+ squares is rare enough to only fit noise
const MOBILITY_CAP: [usize; 6] = [0, 8, 13, 14, 21, 0];
/// Squares around the enemy king attacked, by attacker type knight..queen (KING_ZONE + type - 1)
const KING_ZONE: usize = 80;
/// Pieces attacking the enemy king zone, squared: one attacker is rarely dangerous, three are
const KING_ATTACKERS_SQ: usize = 84;
const PAWN_THREAT: usize = 85; // Our pawn attacks an enemy piece
const MINOR_THREAT: usize = 86; // Our knight or bishop attacks an enemy rook or queen
const ROOK_THREAT: usize = 87; // Our rook attacks an enemy queen
const HANGING: usize = 88; // Enemy piece we attack that nothing defends
const KNIGHT_OUTPOST: usize = 89; // On ranks 4-6, defended by a pawn, no enemy pawn can ever attack it
const BISHOP_OUTPOST: usize = 90;
const PASSED_BLOCKED: usize = 91; // Something stands on the passed pawn's next square
const PASSED_OWN_KING: usize = 92; // King distance to the passed pawn's next square, summed
const PASSED_ENEMY_KING: usize = 93;
const PAWN_SUPPORTED: usize = 94; // Defended by a pawn
const PAWN_PHALANX: usize = 95; // A pawn beside it on the same rank
const TEMPO: usize = 96; // Side to move
const ROOK_SEVENTH: usize = 97;
const SAFE_CHECKS: usize = 98; // Squares a piece could give check from that the enemy doesn't attack
pub const NUM_TERMS: usize = 99;

const FILE_A: u64 = 0x0101_0101_0101_0101;
const FILE_H: u64 = FILE_A << 7;

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

#[inline]
fn pawn_attacks_of(pawns: u64, color: usize) -> u64 {
    if color == WHITE {
        ((pawns & !FILE_A) << 7) | ((pawns & !FILE_H) << 9)
    } else {
        ((pawns & !FILE_A) >> 9) | ((pawns & !FILE_H) >> 7)
    }
}

#[inline]
fn distance(a: usize, b: usize) -> i32 {
    let df = (a % 8) as i32 - (b % 8) as i32;
    let dr = (a / 8) as i32 - (b / 8) as i32;
    df.abs().max(dr.abs())
}

#[inline]
fn piece_attacks(piece: usize, sq: usize, occ: u64) -> u64 {
    match piece {
        KNIGHT => KNIGHT_ATTACKS[sq],
        BISHOP => bishop_attacks(sq, occ),
        ROOK => rook_attacks(sq, occ),
        QUEEN => bishop_attacks(sq, occ) | rook_attacks(sq, occ),
        _ => KING_ATTACKS[sq],
    }
}

/// Count of each positional term, White's minus Black's. The evaluation is the dot product of
/// these with TERM_MG / TERM_EG (plus the piece-square part), which is what lets the tuner fit
/// every weight by linear regression.
pub fn term_counts(b: &Board) -> [i32; NUM_TERMS] {
    let mut counts = [0i32; NUM_TERMS];
    let occ = b.occupied();
    // Attack maps: by piece type and in total, per colour
    let mut attacks = [[0u64; 6]; 2];
    let mut all_attacks = [0u64; 2];
    for color in [WHITE, BLACK] {
        attacks[color][PAWN] = pawn_attacks_of(b.pieces[PAWN] & b.colors[color], color);
        for piece in KNIGHT..=KING {
            let mut bb = b.pieces[piece] & b.colors[color];
            while bb != 0 {
                attacks[color][piece] |= piece_attacks(piece, pop_lsb(&mut bb), occ);
            }
        }
        all_attacks[color] = attacks[color].iter().fold(0, |a, &x| a | x);
    }

    counts[TEMPO] = if b.side == WHITE { 1 } else { -1 };

    for color in [WHITE, BLACK] {
        let enemy = color ^ 1;
        let sign = if color == WHITE { 1 } else { -1 };
        let own = b.colors[color];
        let them = b.colors[enemy];
        let own_pawns = b.pieces[PAWN] & own;
        let enemy_pawns = b.pieces[PAWN] & them;
        let file_has = |pawns: u64, f: usize| pawns & (FILE_A << f) != 0;
        let relative_rank = |sq: usize| if color == WHITE { sq / 8 } else { 7 - sq / 8 }; // 0..7

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

        let own_king = b.king_square(color);
        let enemy_king = b.king_square(enemy);
        let mut pawns = own_pawns;
        while pawns != 0 {
            let sq = pop_lsb(&mut pawns);
            if PAWN_ATTACKS[enemy][sq] & own_pawns != 0 {
                counts[PAWN_SUPPORTED] += sign;
            }
            let beside = ((bit(sq) & !FILE_A) >> 1) | ((bit(sq) & !FILE_H) << 1);
            if beside & own_pawns != 0 {
                counts[PAWN_PHALANX] += sign;
            }
            if PASSED_MASK[color][sq] & enemy_pawns == 0 {
                // The pawn's rank counted from its own side, 2..=7
                let rank = relative_rank(sq) + 1;
                counts[PASSED + rank - 2] += sign;
                let stop = if color == WHITE { sq + 8 } else { sq - 8 };
                if occ & bit(stop) != 0 {
                    counts[PASSED_BLOCKED] += sign;
                }
                counts[PASSED_OWN_KING] += sign * distance(own_king, stop);
                counts[PASSED_ENEMY_KING] += sign * distance(enemy_king, stop);
            }
        }

        // Pawn shield: own pawns one or two ranks in front of the king, on its file and the two beside it
        let (kf, kr) = ((own_king % 8) as i32, (own_king / 8) as i32);
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

        if (b.pieces[BISHOP] & own).count_ones() >= 2 {
            counts[BISHOP_PAIR] += sign;
        }

        // Pieces: mobility, king attacks, outposts, rooks
        let safe = !own & !attacks[enemy][PAWN];
        let king_zone = KING_ATTACKS[enemy_king] | bit(enemy_king);
        let mut attackers = 0;
        for piece in KNIGHT..=QUEEN {
            let mut bb = b.pieces[piece] & own;
            while bb != 0 {
                let sq = pop_lsb(&mut bb);
                let att = piece_attacks(piece, sq, occ);
                let mobility = ((att & safe).count_ones() as usize).min(MOBILITY_CAP[piece]);
                counts[MOBILITY[piece] + mobility] += sign;
                let zone = (att & king_zone).count_ones() as i32;
                if zone > 0 {
                    counts[KING_ZONE + piece - 1] += sign * zone;
                    attackers += 1;
                }
                if piece == KNIGHT || piece == BISHOP {
                    let rank = relative_rank(sq);
                    // Enemy pawns on adjacent files that could still advance to attack this square
                    let front = PASSED_MASK[color][sq] & !(FILE_A << (sq % 8));
                    if (3..=5).contains(&rank) && PAWN_ATTACKS[enemy][sq] & own_pawns != 0 && front & enemy_pawns == 0 {
                        counts[if piece == KNIGHT { KNIGHT_OUTPOST } else { BISHOP_OUTPOST }] += sign;
                    }
                }
                if piece == ROOK {
                    let f = sq % 8;
                    if !file_has(own_pawns, f) {
                        counts[if file_has(enemy_pawns, f) { ROOK_HALF_OPEN } else { ROOK_OPEN }] += sign;
                    }
                    if relative_rank(sq) == 6 {
                        counts[ROOK_SEVENTH] += sign;
                    }
                }
            }
        }
        counts[KING_ATTACKERS_SQ] += sign * attackers * attackers;

        // Threats
        let majors = b.pieces[ROOK] | b.pieces[QUEEN];
        let pieces = them & !b.pieces[PAWN] & !b.pieces[KING];
        counts[PAWN_THREAT] += sign * (attacks[color][PAWN] & pieces).count_ones() as i32;
        counts[MINOR_THREAT] += sign * ((attacks[color][KNIGHT] | attacks[color][BISHOP]) & them & majors).count_ones() as i32;
        counts[ROOK_THREAT] += sign * (attacks[color][ROOK] & them & b.pieces[QUEEN]).count_ones() as i32;
        counts[HANGING] += sign * (all_attacks[color] & !all_attacks[enemy] & them & !b.pieces[KING]).count_ones() as i32;

        // Safe checks: squares our pieces reach that would check the enemy king, not attacked by them
        let unsafe_for_us = all_attacks[enemy] | own;
        let rook_checks = rook_attacks(enemy_king, occ);
        let bishop_checks = bishop_attacks(enemy_king, occ);
        let checks = (attacks[color][KNIGHT] & KNIGHT_ATTACKS[enemy_king])
            | (attacks[color][BISHOP] & bishop_checks)
            | (attacks[color][ROOK] & rook_checks)
            | (attacks[color][QUEEN] & (rook_checks | bishop_checks));
        counts[SAFE_CHECKS] += sign * (checks & !unsafe_for_us).count_ones() as i32;
    }
    counts
}
