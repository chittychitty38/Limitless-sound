//! Low-level color math: sRGB transfer, OKLab, and color vision simulation.

pub type Rgb = [f64; 3];

pub fn srgb_to_linear(c: f64) -> f64 {
    if c <= 0.04045 {
        c / 12.92
    } else {
        ((c + 0.055) / 1.055).powf(2.4)
    }
}

pub fn linear_to_srgb(c: f64) -> f64 {
    if c <= 0.0031308 {
        12.92 * c
    } else {
        1.055 * c.powf(1.0 / 2.4) - 0.055
    }
}

pub fn clamp01(x: f64) -> f64 {
    x.clamp(0.0, 1.0)
}

pub fn srgb_to_lin3(c: Rgb) -> Rgb {
    c.map(srgb_to_linear)
}

pub fn lin_to_srgb3(c: Rgb) -> Rgb {
    c.map(|v| linear_to_srgb(clamp01(v)))
}

/// Parses `#rrggbb` (the leading `#` is optional) into sRGB 0..1.
pub fn hex_to_srgb(hex: &str) -> Option<Rgb> {
    let h = hex.trim().trim_start_matches('#');
    if h.len() != 6 || !h.chars().all(|c| c.is_ascii_hexdigit()) {
        return None;
    }
    let p = |i: usize| u8::from_str_radix(&h[i..i + 2], 16).ok().map(|v| v as f64 / 255.0);
    Some([p(0)?, p(2)?, p(4)?])
}

pub fn srgb_to_hex(c: Rgb) -> String {
    let b = c.map(|v| (clamp01(v) * 255.0).round() as u8);
    format!("#{:02x}{:02x}{:02x}", b[0], b[1], b[2])
}

pub fn hex_to_lin(hex: &str) -> Option<Rgb> {
    hex_to_srgb(hex).map(srgb_to_lin3)
}

pub fn lin_to_hex(c: Rgb) -> String {
    srgb_to_hex(lin_to_srgb3(c))
}

/// Linear sRGB to OKLab (Björn Ottosson, 2020).
pub fn lin_to_oklab([r, g, b]: Rgb) -> Rgb {
    let l = (0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b).cbrt();
    let m = (0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b).cbrt();
    let s = (0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b).cbrt();
    [
        0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
        1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
        0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s,
    ]
}

pub fn oklab_to_lin([l_, a, b]: Rgb) -> Rgb {
    let l = l_ + 0.3963377774 * a + 0.2158037573 * b;
    let m = l_ - 0.1055613458 * a - 0.0638541728 * b;
    let s = l_ - 0.0894841775 * a - 1.2914855480 * b;
    let (l, m, s) = (l * l * l, m * m * m, s * s * s);
    [
        4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
        -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
        -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s,
    ]
}

pub type Mat3 = [[f64; 3]; 3];

pub fn mul(m: &Mat3, c: Rgb) -> Rgb {
    [
        m[0][0] * c[0] + m[0][1] * c[1] + m[0][2] * c[2],
        m[1][0] * c[0] + m[1][1] * c[1] + m[1][2] * c[2],
        m[2][0] * c[0] + m[2][1] * c[1] + m[2][2] * c[2],
    ]
}

/// Kinds of color vision difference the app corrects for.
#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum CvdType {
    /// Red-weak (protanomaly / protanopia).
    Protan,
    /// Green-weak (deuteranomaly / deuteranopia), the most common.
    Deutan,
    /// Blue-yellow (tritanomaly / tritanopia).
    Tritan,
}

impl CvdType {
    pub const ALL: [CvdType; 3] = [CvdType::Protan, CvdType::Deutan, CvdType::Tritan];

    pub fn plain_name(self) -> &'static str {
        match self {
            CvdType::Protan => "red-green (red-weak)",
            CvdType::Deutan => "red-green (green-weak)",
            CvdType::Tritan => "blue-yellow",
        }
    }

    /// Machado, Oliveira & Fernandes (2009) matrices at full severity, linear RGB.
    pub fn machado(self) -> Mat3 {
        match self {
            CvdType::Protan => [
                [0.152286, 1.052583, -0.204868],
                [0.114503, 0.786281, 0.099216],
                [-0.003882, -0.048116, 1.051998],
            ],
            CvdType::Deutan => [
                [0.367322, 0.860646, -0.227968],
                [0.280085, 0.672501, 0.047413],
                [-0.011820, 0.042940, 0.968881],
            ],
            CvdType::Tritan => [
                [1.255528, -0.076749, -0.178779],
                [-0.078411, 0.930809, 0.147602],
                [0.004733, 0.691367, 0.303900],
            ],
        }
    }

    /// Simulation matrix blended between normal vision (0) and full severity (1).
    pub fn sim_matrix(self, severity: f64) -> Mat3 {
        let m = self.machado();
        let s = severity.clamp(0.0, 1.0);
        let mut out = [[0.0; 3]; 3];
        for i in 0..3 {
            for j in 0..3 {
                let id = if i == j { 1.0 } else { 0.0 };
                out[i][j] = id * (1.0 - s) + m[i][j] * s;
            }
        }
        out
    }
}

/// How a person with this color vision likely sees `lin` (linear in, linear out).
pub fn simulate(lin: Rgb, cvd: CvdType, severity: f64) -> Rgb {
    mul(&cvd.sim_matrix(severity), lin).map(clamp01)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn hex_roundtrip() {
        for h in ["#000000", "#ffffff", "#e5322d", "#3bbf4a"] {
            assert_eq!(srgb_to_hex(hex_to_srgb(h).unwrap()), h);
        }
        assert!(hex_to_srgb("#12345").is_none());
        assert!(hex_to_srgb("zzzzzz").is_none());
    }

    #[test]
    fn oklab_roundtrip() {
        for c in [[0.2, 0.5, 0.9], [1.0, 0.0, 0.0], [0.0, 0.0, 0.0], [0.7, 0.7, 0.7]] {
            let back = oklab_to_lin(lin_to_oklab(c));
            for i in 0..3 {
                assert!((back[i] - c[i]).abs() < 1e-6, "{c:?} -> {back:?}");
            }
        }
    }

    #[test]
    fn simulation_keeps_greys() {
        for t in CvdType::ALL {
            let g = simulate([0.5, 0.5, 0.5], t, 1.0);
            for v in g {
                assert!((v - 0.5).abs() < 0.01, "{t:?} {g:?}");
            }
        }
    }

    #[test]
    fn deutan_confuses_red_and_green() {
        // A red and a green of similar lightness should land much closer together.
        let red = hex_to_lin("#c0582a").unwrap();
        let green = hex_to_lin("#7a8a2a").unwrap();
        let d = |a: Rgb, b: Rgb| {
            let (a, b) = (lin_to_oklab(a), lin_to_oklab(b));
            ((a[0] - b[0]).powi(2) + (a[1] - b[1]).powi(2) + (a[2] - b[2]).powi(2)).sqrt()
        };
        let normal = d(red, green);
        let seen = d(simulate(red, CvdType::Deutan, 1.0), simulate(green, CvdType::Deutan, 1.0));
        assert!(seen < normal * 0.5, "normal {normal} seen {seen}");
    }
}
