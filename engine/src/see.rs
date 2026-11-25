//! Static exchange evaluation (SEE): the material a capture wins or loses once every recapture on
//! that square is played out, each side always recapturing with its least valuable piece and free
//! to stop. Same rules as ChessGame/SEE.py.
//!
//! Sliders hidden behind pieces already used (x-rays) are found by recomputing attackers with the
//! used pieces removed from the occupancy. Pins and checks are ignored, as usual for SEE: it is a
//! fast estimate for move ordering and pruning, not an exact result.

use crate::attacks::*;
use crate::board::*;
use crate::moves::*;

/// Piece values for exchanges. The king's is huge so "capturing" with it is only ever the last step.
const SEE_VALUE: [i32; 6] = [100, 320, 330, 500, 900, 20000];

/// Every piece of either colour attacking `sq`, with `occ` as the occupied squares
#[inline]
fn attackers_to(b: &Board, sq: usize, occ: u64) -> u64 {
    let bishops = b.pieces[BISHOP] | b.pieces[QUEEN];
    let rooks = b.pieces[ROOK] | b.pieces[QUEEN];
    (PAWN_ATTACKS[BLACK][sq] & b.pieces[PAWN] & b.colors[WHITE])
        | (PAWN_ATTACKS[WHITE][sq] & b.pieces[PAWN] & b.colors[BLACK])
        | (KNIGHT_ATTACKS[sq] & b.pieces[KNIGHT])
        | (KING_ATTACKS[sq] & b.pieces[KING])
        | (bishop_attacks(sq, occ) & bishops)
        | (rook_attacks(sq, occ) & rooks)
}

/// Material balance of the exchange `m` starts, in centipawns for the side making it
pub fn see(b: &Board, m: Move) -> i32 {
    if flag(m) == EN_PASSANT {
        return SEE_VALUE[PAWN]; // Recaptures on the empty square are rare enough to ignore
    }
    let from = from_sq(m);
    let to = to_sq(m);

    // gains[d]: balance for the side making capture d if the exchange stopped there
    let mut gains = [0i32; 32];
    gains[0] = if is_capture(m) { SEE_VALUE[b.mailbox[to] as usize % 6] } else { 0 };
    let mut on_square = SEE_VALUE[b.mailbox[from] as usize % 6];
    if is_promotion(m) {
        gains[0] += SEE_VALUE[promotion_piece(m)] - SEE_VALUE[PAWN];
        on_square = SEE_VALUE[promotion_piece(m)];
    }

    let mut occ = b.occupied() ^ bit(from);
    let mut side = b.side ^ 1;
    let mut depth = 0;
    loop {
        let attackers = attackers_to(b, to, occ) & occ & b.colors[side];
        if attackers == 0 {
            break;
        }
        // Least valuable attacker
        let piece = (PAWN..=KING).find(|&p| attackers & b.pieces[p] != 0).unwrap();
        let sq = (attackers & b.pieces[piece]).trailing_zeros() as usize;

        depth += 1;
        gains[depth] = on_square - gains[depth - 1];
        on_square = SEE_VALUE[piece];
        occ ^= bit(sq);
        side ^= 1;
        if piece == KING {
            // A king may only recapture if nothing defends the square
            if attackers_to(b, to, occ) & occ & b.colors[side] != 0 {
                depth -= 1;
            }
            break;
        }
        if depth == gains.len() - 1 {
            break;
        }
    }

    // Each side may decline to continue: fold back from the last capture
    while depth > 0 {
        gains[depth - 1] = -(-gains[depth - 1]).max(gains[depth]);
        depth -= 1;
    }
    gains[0]
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::movegen::legal_moves;

    fn see_of(fen: &str, uci: &str) -> i32 {
        let b = Board::from_fen(fen).unwrap();
        let m = legal_moves(&b).into_iter().find(|&m| to_uci(m) == uci).unwrap();
        see(&b, m)
    }

    #[test]
    fn known_exchanges() {
        // Undefended pawn
        assert_eq!(see_of("1k1r4/1pp4p/p7/4p3/8/P5P1/1PP4P/2K1R3 w - - 0 1", "e1e5"), 100);
        // Pawn defended by a pawn, taken with a knight: lose the knight for a pawn
        assert_eq!(see_of("4k3/8/3p4/4p3/8/5N2/8/4K3 w - - 0 1", "f3e5"), 100 - 320);
        // Rook takes a pawn defended by a rook, backed by a second rook: R+R vs R wins a pawn
        assert_eq!(see_of("3r2k1/8/8/3p4/8/8/3R4/3RK3 w - - 0 1", "d2d5"), 100);
        // x-ray: BxP, PxB, then the queen behind the bishop takes back: bishop for two pawns.
        // Without x-rays the queen would be missed and this would read 100 - 330
        assert_eq!(see_of("4k3/8/3p4/4p3/3B4/2Q5/8/4K3 w - - 0 1", "d4e5"), 200 - 330);
    }
}
