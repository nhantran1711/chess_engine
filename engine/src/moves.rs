//! A move packed into 16 bits: from square (6), to square (6), flag (4).
//! 0 is never a legal move (a1 -> a1), so it doubles as "no move".

pub type Move = u16;

pub const NO_MOVE: Move = 0;

pub const QUIET: u16 = 0;
pub const DOUBLE_PUSH: u16 = 1;
pub const KING_CASTLE: u16 = 2;
pub const QUEEN_CASTLE: u16 = 3;
pub const CAPTURE: u16 = 4;
pub const EN_PASSANT: u16 = 5;
pub const PROMO: u16 = 8; // + 0 knight, 1 bishop, 2 rook, 3 queen
pub const PROMO_CAPTURE: u16 = 12;

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

pub fn square_name(sq: usize) -> String {
    let file = (b'a' + (sq % 8) as u8) as char;
    let rank = (b'1' + (sq / 8) as u8) as char;
    format!("{file}{rank}")
}

pub fn parse_square(s: &str) -> Option<usize> {
    let b = s.as_bytes();
    if b.len() != 2 || !(b'a'..=b'h').contains(&b[0]) || !(b'1'..=b'8').contains(&b[1]) {
        return None;
    }
    Some(((b[1] - b'1') * 8 + (b[0] - b'a')) as usize)
}

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
