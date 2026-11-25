//! Precomputed attack tables, built at compile time.
//!
//! Squares are numbered a1 = 0, b1 = 1, ..., h8 = 63, so bit `sq` of a `u64` is that square.
//! Sliding pieces use ray tables: walk the ray, find the first blocker with a bit scan, and cut
//! the ray off just past it.

pub const fn bit(sq: usize) -> u64 {
    1u64 << sq
}

#[inline(always)]
pub fn pop_lsb(bb: &mut u64) -> usize {
    let sq = bb.trailing_zeros() as usize;
    *bb &= *bb - 1;
    sq
}

const fn leaper(deltas: [(i32, i32); 8]) -> [u64; 64] {
    let mut table = [0u64; 64];
    let mut sq = 0;
    while sq < 64 {
        let file = (sq % 8) as i32;
        let rank = (sq / 8) as i32;
        let mut i = 0;
        while i < 8 {
            let f = file + deltas[i].0;
            let r = rank + deltas[i].1;
            if f >= 0 && f < 8 && r >= 0 && r < 8 {
                table[sq] |= 1u64 << (r * 8 + f) as usize;
            }
            i += 1;
        }
        sq += 1;
    }
    table
}

const fn pawn_table() -> [[u64; 64]; 2] {
    let mut table = [[0u64; 64]; 2];
    let mut sq = 0;
    while sq < 64 {
        let file = sq % 8;
        let rank = sq / 8;
        if rank < 7 {
            if file > 0 {
                table[0][sq] |= bit(sq + 7);
            }
            if file < 7 {
                table[0][sq] |= bit(sq + 9);
            }
        }
        if rank > 0 {
            if file > 0 {
                table[1][sq] |= bit(sq - 9);
            }
            if file < 7 {
                table[1][sq] |= bit(sq - 7);
            }
        }
        sq += 1;
    }
    table
}

// The first four directions increase the square index, the last four decrease it
const DIRECTIONS: [(i32, i32); 8] = [(0, 1), (1, 0), (1, 1), (-1, 1), (0, -1), (-1, 0), (1, -1), (-1, -1)];
const N: usize = 0;
const E: usize = 1;
const NE: usize = 2;
const NW: usize = 3;
const S: usize = 4;
const W: usize = 5;
const SE: usize = 6;
const SW: usize = 7;

const fn ray_table() -> [[u64; 64]; 8] {
    let mut table = [[0u64; 64]; 8];
    let mut dir = 0;
    while dir < 8 {
        let mut sq = 0;
        while sq < 64 {
            let mut f = (sq % 8) as i32 + DIRECTIONS[dir].0;
            let mut r = (sq / 8) as i32 + DIRECTIONS[dir].1;
            while f >= 0 && f < 8 && r >= 0 && r < 8 {
                table[dir][sq] |= 1u64 << (r * 8 + f) as usize;
                f += DIRECTIONS[dir].0;
                r += DIRECTIONS[dir].1;
            }
            sq += 1;
        }
        dir += 1;
    }
    table
}

pub static KNIGHT_ATTACKS: [u64; 64] = leaper([(1, 2), (2, 1), (2, -1), (1, -2), (-1, -2), (-2, -1), (-2, 1), (-1, 2)]);
pub static KING_ATTACKS: [u64; 64] = leaper([(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]);
/// `PAWN_ATTACKS[colour][sq]`: squares a pawn of that colour on `sq` attacks
pub static PAWN_ATTACKS: [[u64; 64]; 2] = pawn_table();
static RAYS: [[u64; 64]; 8] = ray_table();

#[inline(always)]
fn ray(dir: usize, sq: usize, occ: u64) -> u64 {
    let ray = RAYS[dir][sq];
    let blockers = ray & occ;
    if blockers == 0 {
        return ray;
    }
    let first = if dir < 4 { blockers.trailing_zeros() as usize } else { 63 - blockers.leading_zeros() as usize };
    ray ^ RAYS[dir][first]
}

#[inline(always)]
pub fn rook_attacks(sq: usize, occ: u64) -> u64 {
    ray(N, sq, occ) | ray(E, sq, occ) | ray(S, sq, occ) | ray(W, sq, occ)
}

#[inline(always)]
pub fn bishop_attacks(sq: usize, occ: u64) -> u64 {
    ray(NE, sq, occ) | ray(NW, sq, occ) | ray(SE, sq, occ) | ray(SW, sq, occ)
}
