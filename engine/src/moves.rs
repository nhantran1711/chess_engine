//! A move packed into 16 bits: from square (6), to square (6), flag (4).
//! 0 is never a legal move (a1 -> a1), so it doubles as "no move".
//!
//! ```text
//!  15  12 11       6 5        0
//! +------+----------+----------+
//! | flag |    to    |   from   |
//! +------+----------+----------+
//! ```
//!
//! Small moves keep move lists and transposition table entries compact. The flag tells
//! `make_move` everything it can't work out from the two squares: castling, en passant,
//! double pushes and the promotion piece.

pub type Move = u16;

pub const NO_MOVE: Move = 0;

// Flag values, chosen so single bits answer common questions:
// bit 2 (4) = capture (including en passant), bit 3 (8) = promotion,
// and for promotions the low two bits pick the piece.
pub const QUIET: u16 = 0;
pub const DOUBLE_PUSH: u16 = 1;
pub const KING_CASTLE: u16 = 2;
pub const QUEEN_CASTLE: u16 = 3;
pub const CAPTURE: u16 = 4;
pub const EN_PASSANT: u16 = 5;
pub const PROMO: u16 = 8; // + 0 knight, 1 bishop, 2 rook, 3 queen
pub const PROMO_CAPTURE: u16 = 12;

/// Packs a move. Squares must be 0..64 and `flag` one of the constants above.
#[inline(always)]
pub const fn make(from: usize, to: usize, flag: u16) -> Move {
    from as u16 | (to as u16) << 6 | flag << 12
}

#[inline(always)]
pub const fn from_sq(m: Move) -> usize {
    (m & 63) as usize
}

#[inline(always)]
pub const fn to_sq(m: Move) -> usize {
    ((m >> 6) & 63) as usize
}

#[inline(always)]
pub const fn flag(m: Move) -> u16 {
    m >> 12
}

#[inline(always)]
pub const fn is_capture(m: Move) -> bool {
    flag(m) & 4 != 0
}

#[inline(always)]
pub const fn is_promotion(m: Move) -> bool {
    flag(m) & 8 != 0
}

/// Neither a capture nor a promotion
#[inline(always)]
pub const fn is_quiet(m: Move) -> bool {
    flag(m) & 12 == 0
}

/// Piece type promoted to: KNIGHT (1) ..= QUEEN (4)
#[inline(always)]
pub const fn promotion_piece(m: Move) -> usize {
    (flag(m) & 3) as usize + 1
}

/// Algebraic name of a square, e.g. 0 -> "a1", 63 -> "h8".
pub fn square_name(sq: usize) -> String {
    let file = (b'a' + (sq % 8) as u8) as char;
    let rank = (b'1' + (sq / 8) as u8) as char;
    format!("{file}{rank}")
}

/// Inverse of `square_name`. Returns None for anything that isn't a square, rather than panicking
/// on bad input from a GUI or FEN.
pub fn parse_square(s: &str) -> Option<usize> {
    let b = s.as_bytes();
    if b.len() != 2 || !(b'a'..=b'h').contains(&b[0]) || !(b'1'..=b'8').contains(&b[1]) {
        return None;
    }
    Some(((b[1] - b'1') * 8 + (b[0] - b'a')) as usize)
}

/// UCI long algebraic notation: "e2e4", "e7e8q". Castling is the king's move ("e1g1").
/// NO_MOVE prints as "0000", the UCI null move.
pub fn to_uci(m: Move) -> String {
    if m == NO_MOVE {
        return "0000".to_string();
    }
    let mut s = square_name(from_sq(m)) + &square_name(to_sq(m));
    if is_promotion(m) {
        s.push(['n', 'b', 'r', 'q'][promotion_piece(m) - 1]);
    }
    s
}
