//! 3D lookup tables. The screen filter samples one of these on the GPU for every
//! pixel, and the tuner exports the same table as a `.cube` file.

use crate::color::Rgb;
use crate::profile::Profile;

pub const DEFAULT_SIZE: usize = 33;

/// A cube of sRGB-encoded output colors, red index fastest (the `.cube` order).
#[derive(Debug, Clone, PartialEq)]
pub struct Lut3D {
    pub size: usize,
    pub data: Vec<[f32; 3]>,
}

impl Lut3D {
    pub fn identity(size: usize) -> Lut3D {
        Lut3D::from_fn(size, |c| c)
    }

    /// Builds a table from a function on sRGB-encoded colors.
    pub fn from_fn(size: usize, f: impl Fn(Rgb) -> Rgb) -> Lut3D {
        assert!(size >= 2);
        let n = (size - 1) as f64;
        let mut data = Vec::with_capacity(size * size * size);
        for b in 0..size {
            for g in 0..size {
                for r in 0..size {
                    let o = f([r as f64 / n, g as f64 / n, b as f64 / n]);
                    data.push(o.map(|v| v.clamp(0.0, 1.0) as f32));
                }
            }
        }
        Lut3D { size, data }
    }

    pub fn from_profile(p: &Profile, size: usize) -> Lut3D {
        let t = p.transform();
        Lut3D::from_fn(size, |c| t.apply_srgb(c))
    }

    fn at(&self, r: usize, g: usize, b: usize) -> [f32; 3] {
        self.data[(b * self.size + g) * self.size + r]
    }

    /// Trilinear lookup of an sRGB-encoded color.
    pub fn sample(&self, c: Rgb) -> Rgb {
        let n = (self.size - 1) as f64;
        let p = c.map(|v| v.clamp(0.0, 1.0) * n);
        let i0 = p.map(|v| (v.floor() as usize).min(self.size - 1));
        let i1 = i0.map(|v| (v + 1).min(self.size - 1));
        let f = [p[0] - i0[0] as f64, p[1] - i0[1] as f64, p[2] - i0[2] as f64];
        let mut out = [0.0; 3];
        for (k, o) in out.iter_mut().enumerate() {
            let v = |r: usize, g: usize, b: usize| self.at(r, g, b)[k] as f64;
            let x00 = v(i0[0], i0[1], i0[2]) * (1.0 - f[0]) + v(i1[0], i0[1], i0[2]) * f[0];
            let x10 = v(i0[0], i1[1], i0[2]) * (1.0 - f[0]) + v(i1[0], i1[1], i0[2]) * f[0];
            let x01 = v(i0[0], i0[1], i1[2]) * (1.0 - f[0]) + v(i1[0], i0[1], i1[2]) * f[0];
            let x11 = v(i0[0], i1[1], i1[2]) * (1.0 - f[0]) + v(i1[0], i1[1], i1[2]) * f[0];
            let y0 = x00 * (1.0 - f[1]) + x10 * f[1];
            let y1 = x01 * (1.0 - f[1]) + x11 * f[1];
            *o = y0 * (1.0 - f[2]) + y1 * f[2];
        }
        out
    }

    /// RGBA, 8 bits per channel, ready to upload as a 3D texture.
    pub fn to_rgba8(&self) -> Vec<u8> {
        let mut out = Vec::with_capacity(self.data.len() * 4);
        for c in &self.data {
            for v in c {
                out.push((v * 255.0).round() as u8);
            }
            out.push(255);
        }
        out
    }

    pub fn to_cube(&self, title: &str) -> String {
        let mut s = String::with_capacity(self.data.len() * 28 + 200);
        s.push_str(&format!("TITLE \"{}\"\n", title.replace('"', "'")));
        s.push_str("# Made with Limitless Color. Apply to the screen, not to audio.\n");
        s.push_str(&format!("LUT_3D_SIZE {}\nDOMAIN_MIN 0.0 0.0 0.0\nDOMAIN_MAX 1.0 1.0 1.0\n", self.size));
        for c in &self.data {
            s.push_str(&format!("{:.6} {:.6} {:.6}\n", c[0], c[1], c[2]));
        }
        s
    }

    pub fn parse_cube(text: &str) -> Result<Lut3D, String> {
        let mut size = 0usize;
        let mut data = Vec::new();
        for (no, line) in text.lines().enumerate() {
            let line = line.trim();
            if line.is_empty() || line.starts_with('#') {
                continue;
            }
            if let Some(rest) = line.strip_prefix("LUT_3D_SIZE") {
                size = rest.trim().parse().map_err(|_| format!("line {}: bad LUT_3D_SIZE", no + 1))?;
                if !(2..=129).contains(&size) {
                    return Err(format!("line {}: LUT size {size} is out of range", no + 1));
                }
                continue;
            }
            if line.starts_with(|c: char| c.is_ascii_alphabetic()) {
                continue; // TITLE, DOMAIN_MIN, DOMAIN_MAX and other keywords
            }
            let v: Vec<f32> = line.split_whitespace().map(|x| x.parse::<f32>()).collect::<Result<_, _>>().map_err(|_| format!("line {}: expected three numbers", no + 1))?;
            if v.len() != 3 {
                return Err(format!("line {}: expected three numbers", no + 1));
            }
            data.push([v[0], v[1], v[2]]);
        }
        if size == 0 {
            return Err("missing LUT_3D_SIZE".into());
        }
        if data.len() != size * size * size {
            return Err(format!("expected {} entries, found {}", size * size * size, data.len()));
        }
        Ok(Lut3D { size, data })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::color::{hex_to_srgb, srgb_to_hex};

    #[test]
    fn identity_samples_back_exactly() {
        let l = Lut3D::identity(17);
        let c = [0.123, 0.5, 0.987];
        let o = l.sample(c);
        for i in 0..3 {
            assert!((o[i] - c[i]).abs() < 1e-6);
        }
    }

    #[test]
    fn cube_roundtrip() {
        let mut p = Profile::default();
        p.settings.daltonize = 0.6;
        p.settings.red_shift = -25.0;
        let l = Lut3D::from_profile(&p, 9);
        let back = Lut3D::parse_cube(&l.to_cube("test")).unwrap();
        assert_eq!(back.size, 9);
        for (a, b) in l.data.iter().zip(&back.data) {
            for i in 0..3 {
                assert!((a[i] - b[i]).abs() < 1e-5);
            }
        }
    }

    #[test]
    fn lut_tracks_exact_transform() {
        let mut p = Profile::default();
        p.settings.daltonize = 0.5;
        p.settings.rg_split = 0.15;
        p.settings.red_shift = -20.0;
        p.settings.green_shift = 22.0;
        let l = Lut3D::from_profile(&p, DEFAULT_SIZE);
        let t = p.transform();
        for h in ["#e5322d", "#3bbf4a", "#f2d23c", "#2fa9d9", "#8e5bd6"] {
            let c = hex_to_srgb(h).unwrap();
            let exact = t.apply_srgb(c);
            let got = l.sample(c);
            for i in 0..3 {
                assert!((exact[i] - got[i]).abs() < 0.02, "{h}: {} vs {}", srgb_to_hex(exact), srgb_to_hex(got));
            }
        }
    }

    #[test]
    fn rejects_bad_cube() {
        assert!(Lut3D::parse_cube("LUT_3D_SIZE 2\n0 0 0\n").is_err());
        assert!(Lut3D::parse_cube("0 0 0\n").is_err());
    }
}
