//! Fits a profile to a single color matrix. Windows can apply a matrix to the
//! whole screen in the graphics driver at no cost (the Magnification API), so
//! the Windows filter uses the closest matrix to the full profile.

use crate::color::Rgb;
use crate::profile::Profile;

/// out = M · [r, g, b, 1], on sRGB-encoded values.
pub type Affine = [[f64; 4]; 3];

pub const IDENTITY: Affine = [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0]];

/// Least-squares affine fit of the profile over a grid of colors.
/// Saturated colors count double, since that's where the profile does its work.
pub fn fit(p: &Profile) -> Affine {
    if p.is_identity() {
        return IDENTITY;
    }
    let t = p.transform();
    let steps = 9;
    let mut ata = [[0.0f64; 4]; 4];
    let mut atb = [[0.0f64; 4]; 3];
    for bi in 0..steps {
        for gi in 0..steps {
            for ri in 0..steps {
                let c = [ri, gi, bi].map(|v| v as f64 / (steps - 1) as f64);
                let mx = c.iter().cloned().fold(0.0, f64::max);
                let mn = c.iter().cloned().fold(1.0, f64::min);
                let w = 1.0 + (mx - mn);
                let x = [c[0], c[1], c[2], 1.0];
                let y = t.apply_srgb(c);
                for i in 0..4 {
                    for j in 0..4 {
                        ata[i][j] += w * x[i] * x[j];
                    }
                    for k in 0..3 {
                        atb[k][i] += w * x[i] * y[k];
                    }
                }
            }
        }
    }
    let mut m = IDENTITY;
    for k in 0..3 {
        m[k] = solve4(ata, atb[k]);
    }
    m
}

fn solve4(mut a: [[f64; 4]; 4], mut b: [f64; 4]) -> [f64; 4] {
    for col in 0..4 {
        let piv = (col..4).max_by(|&i, &j| a[i][col].abs().total_cmp(&a[j][col].abs())).unwrap();
        a.swap(col, piv);
        b.swap(col, piv);
        let d = a[col][col];
        for row in 0..4 {
            if row != col {
                let f = a[row][col] / d;
                for k in 0..4 {
                    a[row][k] -= f * a[col][k];
                }
                b[row] -= f * b[col];
            }
        }
    }
    [0, 1, 2, 3].map(|i| b[i] / a[i][i])
}

pub fn apply(m: &Affine, c: Rgb) -> Rgb {
    [0, 1, 2].map(|k| (m[k][0] * c[0] + m[k][1] * c[1] + m[k][2] * c[2] + m[k][3]).clamp(0.0, 1.0))
}

/// Average error of the matrix against the full profile, in 0..255 steps.
/// Under about 6 the two look the same; above 15 the matrix is a rough match.
pub fn fit_error(p: &Profile, m: &Affine) -> f64 {
    let t = p.transform();
    let steps = 7;
    let mut sum = 0.0;
    let mut n = 0.0;
    for bi in 0..steps {
        for gi in 0..steps {
            for ri in 0..steps {
                let c = [ri, gi, bi].map(|v| v as f64 / (steps - 1) as f64);
                let a = t.apply_srgb(c);
                let b = apply(m, c);
                sum += ((a[0] - b[0]).powi(2) + (a[1] - b[1]).powi(2) + (a[2] - b[2]).powi(2)).sqrt();
                n += 1.0;
            }
        }
    }
    sum / n * 255.0
}

/// The 5×5 MAGCOLOREFFECT matrix Windows expects: row vector [r g b a 1] times
/// the matrix, so inputs are rows and outputs are columns.
pub fn to_mag_color_effect(m: &Affine) -> [f32; 25] {
    let mut e = [0.0f32; 25];
    for out in 0..3 {
        for inp in 0..3 {
            e[inp * 5 + out] = m[out][inp] as f32;
        }
        e[4 * 5 + out] = m[out][3] as f32;
    }
    e[3 * 5 + 3] = 1.0;
    e[4 * 5 + 4] = 1.0;
    e
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn identity_profile_fits_identity() {
        assert_eq!(fit(&Profile::default()), IDENTITY);
        let e = to_mag_color_effect(&IDENTITY);
        for i in 0..5 {
            assert_eq!(e[i * 5 + i], 1.0);
        }
    }

    #[test]
    fn daltonize_alone_fits_closely() {
        let mut p = Profile::default();
        p.settings.daltonize = 0.7;
        let m = fit(&p);
        let err = fit_error(&p, &m);
        let untouched = fit_error(&p, &IDENTITY);
        // A matrix can't follow the clipping at the edges of the color cube, but
        // it should get most of the way from "no filter" to the full profile.
        assert!(err < untouched * 0.6, "fit error {err}, without filter {untouched}");
    }

    #[test]
    fn mag_layout_puts_offsets_in_last_row() {
        let m: Affine = [[1.0, 0.0, 0.0, 0.1], [0.0, 1.0, 0.0, 0.2], [0.5, 0.0, 1.0, 0.3]];
        let e = to_mag_color_effect(&m);
        assert_eq!(e[20], 0.1);
        assert_eq!(e[21], 0.2);
        assert_eq!(e[22], 0.3);
        assert_eq!(e[0 * 5 + 2], 0.5); // red input feeds blue output
    }
}
