//! Zobrist keys: one random number per (piece, square), castling-rights set, en passant file and
//! side to move. A position's hash is the XOR of the keys for everything in it, so a move updates
//! it by XORing out what it removed and XORing in what it added.

pub struct Zobrist {
    /// `[piece code][square]`, piece code = colour * 6 + type
    pub piece: [[u64; 64]; 12],
    /// One key per castling-rights bitmask (0..16), so a rights change is a single XOR pair
    pub castle: [u64; 16],
    /// By file only: the rank of an en passant square is implied by the side to move
    pub ep: [u64; 8],
    /// XORed in when Black is to move
    pub side: u64,
}

/// xorshift64 pseudo-random step. Quality is plenty for hashing, and with a fixed seed the
/// keys are the same on every run, so hashes (and any bugs involving them) are reproducible.
const fn xorshift(mut s: u64) -> u64 {
    s ^= s << 13;
    s ^= s >> 7;
    s ^= s << 17;
    s
}

const fn generate() -> Zobrist {
    let mut s: u64 = 0x9E37_79B9_7F4A_7C15;
    let mut z = Zobrist { piece: [[0; 64]; 12], castle: [0; 16], ep: [0; 8], side: 0 };
    let mut p = 0;
    // Generate a random number for each piece/square combination.
    while p < 12 {
        let mut sq = 0;
        while sq < 64 {
            s = xorshift(s);
            z.piece[p][sq] = s;
            sq += 1;
        }
        p += 1;
    }

    // Generate a random number for each castling rights combination.
    let mut i = 0;
    while i < 16 {
        s = xorshift(s);
        z.castle[i] = s;
        i += 1;
    }
    
    // Generate a random number for each en passant file.
    let mut i = 0;
    while i < 8 {
        s = xorshift(s);
        z.ep[i] = s;
        i += 1;
    }
    z.side = xorshift(s);
    z
}

/// Evaluated at compile time. `static` rather than `const` so there is one copy in memory
/// instead of the table being inlined at each use.
pub static ZOB: Zobrist = generate();
