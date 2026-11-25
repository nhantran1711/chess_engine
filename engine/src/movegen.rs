//! Pseudo-legal move generation. Moves that leave the mover's king in check are filtered by
//! the caller after `make_move` (see `Board::mover_in_check`), which is cheaper than proving
//! legality up front for the many moves alpha-beta never gets to.

use crate::attacks::*;
use crate::board::*;
use crate::moves::*;

const RANK_2: u64 = 0x0000_0000_0000_FF00;
const RANK_7: u64 = 0x00FF_0000_0000_0000;

pub struct MoveList {
    pub moves: [Move; 256],
    pub len: usize,
}

impl MoveList {
    pub fn new() -> MoveList {
        MoveList { moves: [NO_MOVE; 256], len: 0 }
    }

    #[inline(always)]
    fn push(&mut self, m: Move) {
        self.moves[self.len] = m;
        self.len += 1;
    }

    pub fn iter(&self) -> impl Iterator<Item = Move> + '_ {
        self.moves[..self.len].iter().copied()
    }
}

#[inline(always)]
fn push_promotions(list: &mut MoveList, from: usize, to: usize, base: u16) {
    for piece in (0..4).rev() {
        list.push(make(from, to, base | piece));
    }
}

/// All pseudo-legal moves, or with `captures_only` just captures and promotions (for quiescence)
pub fn generate(b: &Board, list: &mut MoveList, captures_only: bool) {
    let us = b.side;
    let them = us ^ 1;
    let own = b.colors[us];
    let enemy = b.colors[them];
    let occ = own | enemy;

    // Pawns
    let (up, start_rank, promo_rank): (isize, u64, u64) = if us == WHITE { (8, RANK_2, RANK_7) } else { (-8, RANK_7, RANK_2) };
    let mut pawns = b.pieces[PAWN] & own;
    while pawns != 0 {
        let from = pop_lsb(&mut pawns);
        let promotes = bit(from) & promo_rank != 0;
        let to = (from as isize + up) as usize;
        if occ & bit(to) == 0 {
            if promotes {
                push_promotions(list, from, to, PROMO);
            } else if !captures_only {
                list.push(make(from, to, QUIET));
                if bit(from) & start_rank != 0 {
                    let to2 = (to as isize + up) as usize;
                    if occ & bit(to2) == 0 {
                        list.push(make(from, to2, DOUBLE_PUSH));
                    }
                }
            }
        }
        let mut captures = PAWN_ATTACKS[us][from] & enemy;
        while captures != 0 {
            let to = pop_lsb(&mut captures);
            if promotes {
                push_promotions(list, from, to, PROMO_CAPTURE);
            } else {
                list.push(make(from, to, CAPTURE));
            }
        }
        if b.ep != NO_SQ && PAWN_ATTACKS[us][from] & bit(b.ep as usize) != 0 {
            list.push(make(from, b.ep as usize, EN_PASSANT));
        }
    }

    // Pieces
    let targets = if captures_only { enemy } else { !own };
    for piece in KNIGHT..=KING {
        let mut bb = b.pieces[piece] & own;
        while bb != 0 {
            let from = pop_lsb(&mut bb);
            let attacks = match piece {
                KNIGHT => KNIGHT_ATTACKS[from],
                BISHOP => bishop_attacks(from, occ),
                ROOK => rook_attacks(from, occ),
                QUEEN => bishop_attacks(from, occ) | rook_attacks(from, occ),
                _ => KING_ATTACKS[from],
            };
            let mut moves = attacks & targets;
            while moves != 0 {
                let to = pop_lsb(&mut moves);
                list.push(make(from, to, if enemy & bit(to) != 0 { CAPTURE } else { QUIET }));
            }
        }
    }

    // Castling: squares between king and rook empty, king not in check and not passing through
    // an attacked square. Landing in check is caught by the usual legality test.
    if !captures_only {
        let (king_side, queen_side, base) = if us == WHITE {
            (WHITE_KING_SIDE, WHITE_QUEEN_SIDE, 0)
        } else {
            (BLACK_KING_SIDE, BLACK_QUEEN_SIDE, 56)
        };
        let rook = (us * 6 + ROOK) as u8;
        let king_on_e = b.mailbox[base + 4] == (us * 6 + KING) as u8;
        if king_on_e
            && b.castling & king_side != 0
            && b.mailbox[base + 7] == rook
            && occ & (bit(base + 5) | bit(base + 6)) == 0
            && !b.is_attacked(base + 4, them)
            && !b.is_attacked(base + 5, them)
        {
            list.push(make(base + 4, base + 6, KING_CASTLE));
        }
        if king_on_e
            && b.castling & queen_side != 0
            && b.mailbox[base] == rook
            && occ & (bit(base + 1) | bit(base + 2) | bit(base + 3)) == 0
            && !b.is_attacked(base + 4, them)
            && !b.is_attacked(base + 3, them)
        {
            list.push(make(base + 4, base + 2, QUEEN_CASTLE));
        }
    }
}

pub fn legal_moves(b: &Board) -> Vec<Move> {
    let mut list = MoveList::new();
    generate(b, &mut list, false);
    list.iter().filter(|&m| !b.make_move(m).mover_in_check()).collect()
}

pub fn perft(b: &Board, depth: u32) -> u64 {
    if depth == 0 {
        return 1;
    }
    let mut list = MoveList::new();
    generate(b, &mut list, false);
    let mut nodes = 0;
    for m in list.iter() {
        let next = b.make_move(m);
        if next.mover_in_check() {
            continue;
        }
        nodes += if depth == 1 { 1 } else { perft(&next, depth - 1) };
    }
    nodes
}

#[cfg(test)]
mod tests {
    use super::*;

    const KIWIPETE: &str = "r3k2r/p1ppqpb1/bn2pnp1/3PN3/1p2P3/2N2Q1p/PPPBBPPP/R3K2R w KQkq - 0 1";
    const POSITION_3: &str = "8/2p5/3p4/KP5r/1R3p1k/8/4P1P1/8 w - - 0 1";
    const POSITION_4: &str = "r3k2r/Pppp1ppp/1b3nbN/nP6/BBP1P3/q4N2/Pp1P2PP/R2Q1RK1 w kq - 0 1";
    const POSITION_4_MIRRORED: &str = "r2q1rk1/pP1p2pp/Q4n2/bbp1p3/Np6/1B3NBn/pPPP1PPP/R3K2R b KQ - 0 1";
    const POSITION_5: &str = "rnbq1k1r/pp1Pbppp/2p5/8/2B5/8/PPP1NnPP/RNBQK2R w KQ - 1 8";
    const POSITION_6: &str = "r4rk1/1pp1qppp/p1np1n2/2b1p1B1/2B1P1b1/P1NP1N2/1PP1QPPP/R4RK1 w - - 0 10";

    // https://www.chessprogramming.org/Perft_Results
    #[test]
    fn perft_reference_counts() {
        let cases: &[(&str, u32, u64)] = &[
            (START_FEN, 5, 4_865_609),
            (KIWIPETE, 4, 4_085_603),
            (POSITION_3, 6, 11_030_083),
            (POSITION_4, 5, 15_833_292),
            (POSITION_4_MIRRORED, 5, 15_833_292),
            (POSITION_5, 4, 2_103_487),
            (POSITION_6, 4, 3_894_594),
        ];
        for &(fen, depth, expected) in cases {
            assert_eq!(perft(&Board::from_fen(fen).unwrap(), depth), expected, "{fen} depth {depth}");
        }
    }

    // The incrementally updated hash must match a from-scratch hash everywhere
    #[test]
    fn incremental_hash_matches_full_hash() {
        fn walk(b: &Board, depth: u32) {
            assert_eq!(b.hash, b.compute_hash());
            if depth == 0 {
                return;
            }
            for m in legal_moves(b) {
                walk(&b.make_move(m), depth - 1);
            }
        }
        for fen in [START_FEN, KIWIPETE, POSITION_3, POSITION_4, POSITION_5] {
            walk(&Board::from_fen(fen).unwrap(), 3);
        }
    }

    // Quiescence generator must give exactly the legal captures and promotions
    #[test]
    fn capture_generator_matches_full_generator() {
        for fen in [KIWIPETE, POSITION_3, POSITION_4, POSITION_5, POSITION_6] {
            let b = Board::from_fen(fen).unwrap();
            for m in legal_moves(&b) {
                let next = b.make_move(m);
                let mut all: Vec<Move> = legal_moves(&next).into_iter().filter(|&m| !is_quiet(m)).collect();
                let mut list = MoveList::new();
                generate(&next, &mut list, true);
                let mut caps: Vec<Move> = list.iter().filter(|&m| !next.make_move(m).mover_in_check()).collect();
                all.sort();
                caps.sort();
                assert_eq!(all, caps, "{fen} after {}", to_uci(m));
            }
        }
    }
}
