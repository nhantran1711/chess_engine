//! Texel tuning of every evaluation weight, in Rust, writing engine/src/params.rs.
//!
//!     chessgame tune positions.epd [epochs]
//!
//! Each line holds a FEN (first four fields are enough) and the game result, as in the
//! quiet-labeled.v7 set: `<fen> c9 "1-0";` (or "0-1", "1/2-1/2"). The evaluation is linear in
//! its weights for a fixed position (piece-square entries plus `eval::term_counts`, tapered by
//! phase), so the fit is a logistic regression:
//!
//! ```text
//! p = 1 / (1 + 10^(-K * eval / 400)),  minimise mean (result - p)^2
//! ```
//!
//! K is fitted once with the starting weights and then held fixed. The weights are fitted with
//! Adam on the full batch. Material values stay as they are while tuning; afterwards each piece's
//! average table entry is folded into its material value so the tables stay centred on zero.

use crate::attacks::pop_lsb;
use crate::board::*;
use crate::eval::{term_counts, MAX_PHASE, NUM_TERMS, PHASE};
use crate::params::*;
use std::fmt::Write as _;

const NUM_PST: usize = 6 * 64;
/// Weights per game phase: piece-square entries, then terms. MG block first, then EG.
const HALF: usize = NUM_PST + NUM_TERMS;

struct Position {
    /// Feature index (< HALF) and count, White's minus Black's
    features: Vec<(u16, i8)>,
    /// Material values (fixed while tuning) in mg and eg
    base: (f32, f32),
    phase: f32,
    result: f32,
}

fn load(path: &str) -> Vec<Position> {
    let text = std::fs::read_to_string(path).expect("positions file");
    let mut out = Vec::new();
    for line in text.lines() {
        let result = if line.contains("\"1-0\"") {
            1.0
        } else if line.contains("\"0-1\"") {
            0.0
        } else if line.contains("\"1/2-1/2\"") {
            0.5
        } else {
            continue;
        };
        let fen: Vec<&str> = line.split_whitespace().take(4).collect();
        let Ok(b) = Board::from_fen(&fen.join(" ")) else { continue };
        let mut features: Vec<(u16, i8)> = Vec::with_capacity(48);
        let (mut base_mg, mut base_eg, mut phase) = (0i32, 0i32, 0i32);
        for color in [WHITE, BLACK] {
            let sign: i8 = if color == WHITE { 1 } else { -1 };
            for piece in PAWN..=KING {
                let mut bb = b.pieces[piece] & b.colors[color];
                phase += PHASE[piece] * bb.count_ones() as i32;
                while bb != 0 {
                    let sq = pop_lsb(&mut bb);
                    let table_sq = if color == WHITE { sq ^ 56 } else { sq };
                    features.push(((piece * 64 + table_sq) as u16, sign));
                    base_mg += sign as i32 * MG_VALUE[piece];
                    base_eg += sign as i32 * EG_VALUE[piece];
                }
            }
        }
        for (i, &c) in term_counts(&b).iter().enumerate() {
            if c != 0 {
                features.push(((NUM_PST + i) as u16, c.clamp(-127, 127) as i8));
            }
        }
        out.push(Position {
            features,
            base: (base_mg as f32, base_eg as f32),
            phase: phase.min(MAX_PHASE) as f32 / MAX_PHASE as f32,
            result,
        });
    }
    out
}

fn evaluate(p: &Position, w: &[f64]) -> f64 {
    let (mut mg, mut eg) = (p.base.0 as f64, p.base.1 as f64);
    for &(i, c) in &p.features {
        mg += w[i as usize] * c as f64;
        eg += w[HALF + i as usize] * c as f64;
    }
    mg * p.phase as f64 + eg * (1.0 - p.phase as f64)
}

fn sigmoid(k: f64, e: f64) -> f64 {
    1.0 / (1.0 + 10f64.powf(-k * e / 400.0))
}

fn loss(data: &[Position], w: &[f64], k: f64) -> f64 {
    let threads = std::thread::available_parallelism().map(|n| n.get()).unwrap_or(4);
    let chunk = data.len().div_ceil(threads);
    let total: f64 = std::thread::scope(|s| {
        let handles: Vec<_> = data
            .chunks(chunk)
            .map(|part| s.spawn(move || part.iter().map(|p| (p.result as f64 - sigmoid(k, evaluate(p, w))).powi(2)).sum::<f64>()))
            .collect();
        handles.into_iter().map(|h| h.join().unwrap()).sum()
    });
    total / data.len() as f64
}

fn gradient(data: &[Position], w: &[f64], k: f64) -> Vec<f64> {
    let threads = std::thread::available_parallelism().map(|n| n.get()).unwrap_or(4);
    let chunk = data.len().div_ceil(threads);
    let parts: Vec<Vec<f64>> = std::thread::scope(|s| {
        let handles: Vec<_> = data
            .chunks(chunk)
            .map(|part| {
                s.spawn(move || {
                    let mut g = vec![0.0; 2 * HALF];
                    for p in part {
                        let sig = sigmoid(k, evaluate(p, w));
                        // d(loss)/d(eval), up to the constant 2 * K * ln(10) / 400 folded into the learning rate
                        let d = -(p.result as f64 - sig) * sig * (1.0 - sig);
                        let (dm, de) = (d * p.phase as f64, d * (1.0 - p.phase as f64));
                        for &(i, c) in &p.features {
                            g[i as usize] += dm * c as f64;
                            g[HALF + i as usize] += de * c as f64;
                        }
                    }
                    g
                })
            })
            .collect();
        handles.into_iter().map(|h| h.join().unwrap()).collect()
    });
    let mut g = vec![0.0; 2 * HALF];
    for part in parts {
        for (a, b) in g.iter_mut().zip(part) {
            *a += b;
        }
    }
    let n = data.len() as f64;
    g.iter_mut().for_each(|x| *x /= n);
    g
}

/// K minimising the loss with the starting weights (golden-section search)
fn fit_k(data: &[Position], w: &[f64]) -> f64 {
    let (mut lo, mut hi) = (0.1f64, 3.0f64);
    let phi = (5f64.sqrt() - 1.0) / 2.0;
    for _ in 0..30 {
        let a = hi - phi * (hi - lo);
        let b = lo + phi * (hi - lo);
        if loss(data, w, a) < loss(data, w, b) {
            hi = b;
        } else {
            lo = a;
        }
    }
    (lo + hi) / 2.0
}

fn table_text(name: &str, values: &[i32]) -> String {
    let mut s = format!("    // {name}\n    [\n");
    for r in 0..8 {
        let row: Vec<String> = values[r * 8..r * 8 + 8].iter().map(|v| format!("{v:5}")).collect();
        let _ = writeln!(s, "        {},", row.join(", "));
    }
    s + "    ],\n"
}

fn write_params(path: &str, w: &[f64]) {
    let mut values = [MG_VALUE, EG_VALUE];
    let mut tables = [[[0i32; 64]; 6]; 2];
    for phase in 0..2 {
        for piece in PAWN..=KING {
            let entries: Vec<f64> = (0..64).map(|sq| w[phase * HALF + piece * 64 + sq]).collect();
            // Pawns never stand on the first or last rank
            let valid: Vec<usize> = (0..64).filter(|&sq| piece != PAWN || (8..56).contains(&sq)).collect();
            let mean = if piece == KING { 0.0 } else { valid.iter().map(|&sq| entries[sq]).sum::<f64>() / valid.len() as f64 };
            values[phase][piece] += mean.round() as i32;
            for &sq in &valid {
                tables[phase][piece][sq] = (entries[sq] - mean.round()).round() as i32;
            }
        }
    }
    let terms: [Vec<i32>; 2] = [0, 1].map(|phase| (0..NUM_TERMS).map(|i| w[phase * HALF + NUM_PST + i].round() as i32).collect());

    let mut s = String::new();
    s += "//! Evaluation weights in centipawns. GENERATED by `chessgame tune` (engine/src/tune.rs):\n";
    s += "//! re-run the tuner rather than editing by hand.\n//!\n";
    s += "//! Tables are from White's point of view, rank 8 first. TERM_* are indexed by the term\n";
    s += "//! constants in eval.rs.\n\n";
    s += "/// Material by piece type: pawn, knight, bishop, rook, queen, king\n";
    let _ = writeln!(s, "pub const MG_VALUE: [i32; 6] = {:?};", values[0]);
    let _ = writeln!(s, "pub const EG_VALUE: [i32; 6] = {:?};\n", values[1]);
    for (phase, name) in [(0, "MG_TABLE"), (1, "EG_TABLE")] {
        let _ = writeln!(s, "#[rustfmt::skip]\npub const {name}: [[i32; 64]; 6] = [");
        for (piece, letter) in ["P", "N", "B", "R", "Q", "K"].iter().enumerate() {
            s += &table_text(letter, &tables[phase][piece]);
        }
        s += "];\n\n";
    }
    let _ = writeln!(s, "#[rustfmt::skip]\npub const TERM_MG: [i32; {NUM_TERMS}] = {:?};", terms[0]);
    let _ = writeln!(s, "#[rustfmt::skip]\npub const TERM_EG: [i32; {NUM_TERMS}] = {:?};", terms[1]);
    std::fs::write(path, s).expect("write params.rs");
}

pub fn run(args: &[String]) {
    let path = args.first().expect("chessgame tune <positions.epd> [epochs] [out.rs]");
    let epochs: usize = args.get(1).and_then(|e| e.parse().ok()).unwrap_or(2000);
    let out = args.get(2).cloned().unwrap_or_else(|| "src/params.rs".to_string());
    let data = load(path);
    println!("{} positions, {} weights", data.len(), 2 * HALF);

    // Starting weights: the current tables and terms (material is in `base`)
    let mut w = vec![0.0; 2 * HALF];
    for piece in 0..6 {
        for sq in 0..64 {
            w[piece * 64 + sq] = MG_TABLE[piece][sq] as f64;
            w[HALF + piece * 64 + sq] = EG_TABLE[piece][sq] as f64;
        }
    }
    for i in 0..NUM_TERMS {
        w[NUM_PST + i] = TERM_MG[i] as f64;
        w[HALF + NUM_PST + i] = TERM_EG[i] as f64;
    }

    let k = fit_k(&data, &w);
    println!("K = {k:.4}, starting loss {:.6}", loss(&data, &w, k));

    // Adam
    let (lr, b1, b2, eps) = (1.0f64, 0.9f64, 0.999f64, 1e-8f64);
    let mut m = vec![0.0; 2 * HALF];
    let mut v = vec![0.0; 2 * HALF];
    for epoch in 1..=epochs {
        let g = gradient(&data, &w, k);
        for i in 0..w.len() {
            m[i] = b1 * m[i] + (1.0 - b1) * g[i];
            v[i] = b2 * v[i] + (1.0 - b2) * g[i] * g[i];
            let mh = m[i] / (1.0 - b1.powi(epoch as i32));
            let vh = v[i] / (1.0 - b2.powi(epoch as i32));
            w[i] -= lr * mh / (vh.sqrt() + eps);
        }
        if epoch % 100 == 0 || epoch == epochs {
            println!("epoch {epoch}: loss {:.6}", loss(&data, &w, k));
            write_params(&out, &w);
        }
    }
    println!("wrote {out}");
}
