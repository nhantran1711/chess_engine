//! Bitboard position. Copy-make: `make_move` returns a new board and leaves this one untouched,
//! so there is no undo. The struct is small (about 180 bytes), so copying is cheap.

use crate::attacks::*;
use crate::moves::*;
use crate::zobrist::ZOB;

pub const WHITE: usize = 0;
pub const BLACK: usize = 1;

pub const PAWN: usize = 0;
pub const KNIGHT: usize = 1;
pub const BISHOP: usize = 2;
pub const ROOK: usize = 3;
pub const QUEEN: usize = 4;
pub const KING: usize = 5;

/// Pieces are coded colour * 6 + type; this marks an empty square
pub const NO_PIECE: u8 = 12;
pub const NO_SQ: u8 = 64;

pub const WHITE_KING_SIDE: u8 = 1;
pub const WHITE_QUEEN_SIDE: u8 = 2;
pub const BLACK_KING_SIDE: u8 = 4;
pub const BLACK_QUEEN_SIDE: u8 = 8;

pub const START_FEN: &str = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

// Castling rights kept when a move touches a square: moving from or capturing on a king or
// rook's starting square loses the matching rights
static CASTLE_MASK: [u8; 64] = {
    let mut mask = [15u8; 64];
    mask[0] = 15 & !WHITE_QUEEN_SIDE;
    mask[4] = 15 & !(WHITE_KING_SIDE | WHITE_QUEEN_SIDE);
    mask[7] = 15 & !WHITE_KING_SIDE;
    mask[56] = 15 & !BLACK_QUEEN_SIDE;
    mask[60] = 15 & !(BLACK_KING_SIDE | BLACK_QUEEN_SIDE);
    mask[63] = 15 & !BLACK_KING_SIDE;
    mask
};

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub struct Board {
    pub pieces: [u64; 6], // By type, both colours
    pub colors: [u64; 2],
    pub mailbox: [u8; 64],
    pub side: usize,
    pub castling: u8,
    pub ep: u8, // Square a pawn can capture onto en passant, or NO_SQ
    pub halfmove: u16,
    pub fullmove: u16,
    pub hash: u64,
}

impl Board {
    pub fn startpos() -> Board {
        Board::from_fen(START_FEN).unwrap()
    }

    pub fn from_fen(fen: &str) -> Result<Board, String> {
        let fields: Vec<&str> = fen.split_whitespace().collect();
        if fields.len() < 4 {
            return Err(format!("bad fen: {fen}"));
        }
        let mut b = Board {
            pieces: [0; 6],
            colors: [0; 2],
            mailbox: [NO_PIECE; 64],
            side: WHITE,
            castling: 0,
            ep: NO_SQ,
            halfmove: 0,
            fullmove: 1,
            hash: 0,
        };

        let ranks: Vec<&str> = fields[0].split('/').collect();
        if ranks.len() != 8 {
            return Err(format!("bad fen placement: {}", fields[0]));
        }
        for (i, rank_str) in ranks.iter().enumerate() {
            let rank = 7 - i;
            let mut file = 0;
            for ch in rank_str.chars() {
                if let Some(n) = ch.to_digit(10) {
                    file += n as usize;
                    continue;
                }
                let color = if ch.is_ascii_uppercase() { WHITE } else { BLACK };
                let piece_type = match ch.to_ascii_lowercase() {
                    'p' => PAWN,
                    'n' => KNIGHT,
                    'b' => BISHOP,
                    'r' => ROOK,
                    'q' => QUEEN,
                    'k' => KING,
                    _ => return Err(format!("bad fen piece: {ch}")),
                };
                if file > 7 {
                    return Err(format!("bad fen rank: {rank_str}"));
                }
                b.put(rank * 8 + file, (color * 6 + piece_type) as u8);
                file += 1;
            }
        }
        if (b.pieces[KING] & b.colors[WHITE]).count_ones() != 1 || (b.pieces[KING] & b.colors[BLACK]).count_ones() != 1 {
            return Err("fen needs exactly one king per side".to_string());
        }

        b.side = if fields[1] == "b" { BLACK } else { WHITE };
        for ch in fields[2].chars() {
            b.castling |= match ch {
                'K' => WHITE_KING_SIDE,
                'Q' => WHITE_QUEEN_SIDE,
                'k' => BLACK_KING_SIDE,
                'q' => BLACK_QUEEN_SIDE,
                _ => 0,
            };
        }
        if fields[3] != "-" {
            b.ep = parse_square(fields[3]).ok_or(format!("bad fen en passant: {}", fields[3]))? as u8;
        }
        b.halfmove = fields.get(4).and_then(|s| s.parse().ok()).unwrap_or(0);
        b.fullmove = fields.get(5).and_then(|s| s.parse().ok()).unwrap_or(1);
        b.hash = b.compute_hash();
        Ok(b)
    }

    pub fn compute_hash(&self) -> u64 {
        let mut h = 0;
        for sq in 0..64 {
            let p = self.mailbox[sq];
            if p != NO_PIECE {
                h ^= ZOB.piece[p as usize][sq];
            }
        }
        h ^= ZOB.castle[self.castling as usize];
        if self.ep != NO_SQ {
            h ^= ZOB.ep[(self.ep & 7) as usize];
        }
        if self.side == BLACK {
            h ^= ZOB.side;
        }
        h
    }

    #[inline(always)]
    pub fn occupied(&self) -> u64 {
        self.colors[WHITE] | self.colors[BLACK]
    }

    #[inline(always)]
    pub fn king_square(&self, color: usize) -> usize {
        (self.pieces[KING] & self.colors[color]).trailing_zeros() as usize
    }

    #[inline(always)]
    fn put(&mut self, sq: usize, piece: u8) {
        let b = bit(sq);
        self.pieces[piece as usize % 6] |= b;
        self.colors[piece as usize / 6] |= b;
        self.mailbox[sq] = piece;
        self.hash ^= ZOB.piece[piece as usize][sq];
    }

    #[inline(always)]
    fn remove(&mut self, sq: usize) {
        let piece = self.mailbox[sq];
        let b = bit(sq);
        self.pieces[piece as usize % 6] &= !b;
        self.colors[piece as usize / 6] &= !b;
        self.mailbox[sq] = NO_PIECE;
        self.hash ^= ZOB.piece[piece as usize][sq];
    }

    /// Is `sq` attacked by a piece of colour `by`?
    #[inline]
    pub fn is_attacked(&self, sq: usize, by: usize) -> bool {
        let them = self.colors[by];
        let occ = self.occupied();
        // A pawn of `by` attacks sq exactly when a pawn of the other colour on sq would attack it
        PAWN_ATTACKS[by ^ 1][sq] & self.pieces[PAWN] & them != 0
            || KNIGHT_ATTACKS[sq] & self.pieces[KNIGHT] & them != 0
            || KING_ATTACKS[sq] & self.pieces[KING] & them != 0
            || bishop_attacks(sq, occ) & (self.pieces[BISHOP] | self.pieces[QUEEN]) & them != 0
            || rook_attacks(sq, occ) & (self.pieces[ROOK] | self.pieces[QUEEN]) & them != 0
    }

    #[inline]
    pub fn in_check(&self) -> bool {
        self.is_attacked(self.king_square(self.side), self.side ^ 1)
    }

    /// Did the move that produced this board leave the mover's own king attacked?
    #[inline]
    pub fn mover_in_check(&self) -> bool {
        let mover = self.side ^ 1;
        self.is_attacked(self.king_square(mover), self.side)
    }

    /// Plays a pseudo-legal move. The result may leave the mover in check: test with `mover_in_check`.
    pub fn make_move(&self, m: Move) -> Board {
        let mut b = *self;
        let us = self.side;
        let from = from_sq(m);
        let to = to_sq(m);
        let f = flag(m);
        let piece = self.mailbox[from];

        b.halfmove += 1;
        if self.ep != NO_SQ {
            b.hash ^= ZOB.ep[(self.ep & 7) as usize];
            b.ep = NO_SQ;
        }

        if f == EN_PASSANT {
            b.remove(to ^ 8); // The captured pawn is on the mover's side of the target square
            b.halfmove = 0;
        } else if is_capture(m) {
            b.remove(to);
            b.halfmove = 0;
        }
        if piece as usize % 6 == PAWN {
            b.halfmove = 0;
        }

        b.remove(from);
        let placed = if is_promotion(m) { (us * 6 + promotion_piece(m)) as u8 } else { piece };
        b.put(to, placed);

        if f == KING_CASTLE {
            let rook = b.mailbox[to + 1];
            b.remove(to + 1);
            b.put(to - 1, rook);
        } else if f == QUEEN_CASTLE {
            let rook = b.mailbox[to - 2];
            b.remove(to - 2);
            b.put(to + 1, rook);
        } else if f == DOUBLE_PUSH {
            b.ep = ((from + to) / 2) as u8;
            b.hash ^= ZOB.ep[(b.ep & 7) as usize];
        }

        b.hash ^= ZOB.castle[b.castling as usize];
        b.castling &= CASTLE_MASK[from] & CASTLE_MASK[to];
        b.hash ^= ZOB.castle[b.castling as usize];

        if us == BLACK {
            b.fullmove += 1;
        }
        b.side ^= 1;
        b.hash ^= ZOB.side;
        b
    }
}
