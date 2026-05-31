#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct BgraPixel {
    pub blue: u8,
    pub green: u8,
    pub red: u8,
    pub alpha: u8,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct OrbBitmap {
    pub size: u32,
    pub pixels: Vec<BgraPixel>,
}

pub const ORB_BITMAP_SIZE: u32 = 88;

const SUPERSAMPLE: u32 = 4;
const BODY_RADIUS_RATIO: f64 = 0.445;
const SHADOW_OFFSET_Y_RATIO: f64 = 0.06;
const SHADOW_RADIUS_RATIO: f64 = 0.48;
const MARK_HALF_WIDTH_RATIO: f64 = 0.032;
const MARK_HALF_HEIGHT_RATIO: f64 = 0.18;
const STATUS_CENTER_X_RATIO: f64 = 0.78;
const STATUS_CENTER_Y_RATIO: f64 = 0.78;
const STATUS_RADIUS_RATIO: f64 = 0.073;
const STATUS_BORDER_RADIUS_RATIO: f64 = 0.090;

impl OrbBitmap {
    pub fn pixel(&self, x: u32, y: u32) -> BgraPixel {
        self.pixels[(y * self.size + x) as usize]
    }
}

pub fn render_orb_bitmap(size: u32) -> OrbBitmap {
    assert!(size > 0, "orb bitmap size must be positive");

    let mut pixels = Vec::with_capacity((size * size) as usize);
    for y in 0..size {
        for x in 0..size {
            pixels.push(render_pixel(size, x, y));
        }
    }

    OrbBitmap { size, pixels }
}

pub fn render_default_orb_bitmap() -> OrbBitmap {
    crate::asset::render_default_orb_asset(ORB_BITMAP_SIZE)
        .unwrap_or_else(|_| render_orb_bitmap(ORB_BITMAP_SIZE))
}

pub fn orb_bitmap_to_bgra_bytes(bitmap: &OrbBitmap) -> Vec<u8> {
    let mut bytes = Vec::with_capacity(bitmap.pixels.len() * 4);
    for pixel in &bitmap.pixels {
        bytes.extend([pixel.blue, pixel.green, pixel.red, pixel.alpha]);
    }
    bytes
}

fn render_pixel(size: u32, x: u32, y: u32) -> BgraPixel {
    let mut color_sum = LinearColor::default();
    let sample_count = (SUPERSAMPLE * SUPERSAMPLE) as f64;

    for sample_y in 0..SUPERSAMPLE {
        for sample_x in 0..SUPERSAMPLE {
            let px = x as f64 + (sample_x as f64 + 0.5) / SUPERSAMPLE as f64;
            let py = y as f64 + (sample_y as f64 + 0.5) / SUPERSAMPLE as f64;
            color_sum = color_sum.add(sample_color(size as f64, px, py));
        }
    }

    color_sum.scale(1.0 / sample_count).to_bgra_premultiplied()
}

fn sample_color(size: f64, x: f64, y: f64) -> LinearColor {
    let center = size / 2.0;
    let dx = x - center;
    let dy = y - center;
    let distance = (dx * dx + dy * dy).sqrt();
    let body_radius = size * BODY_RADIUS_RATIO;
    let shadow_radius = size * SHADOW_RADIUS_RATIO;

    let mut color = LinearColor::default();

    let shadow_dy = y - (center + size * SHADOW_OFFSET_Y_RATIO);
    let shadow_distance = (dx * dx + shadow_dy * shadow_dy).sqrt();
    if shadow_distance <= shadow_radius {
        let fade = 1.0 - shadow_distance / shadow_radius;
        color = color.over(LinearColor::rgba(0.0, 0.0, 0.0, 0.22 * fade * fade));
    }

    if distance <= body_radius {
        let light = ((-dx * 0.65 - dy * 0.85) / body_radius).clamp(-1.0, 1.0);
        let shade = ((dx * 0.45 + dy * 0.75) / body_radius).clamp(0.0, 1.0);
        let red = (0.04 + light.max(0.0) * 0.07 - shade * 0.02).clamp(0.0, 1.0);
        let green = (0.62 + light.max(0.0) * 0.24 - shade * 0.18).clamp(0.0, 1.0);
        let blue = (0.56 + light.max(0.0) * 0.24 - shade * 0.20).clamp(0.0, 1.0);
        color = color.over(LinearColor::rgba(red, green, blue, 1.0));
    }

    let lower_shadow_x = center + body_radius * 0.30;
    let lower_shadow_y = center + body_radius * 0.36;
    let lower_shadow_radius = body_radius * 0.58;
    let lower_shadow_distance = point_distance(x, y, lower_shadow_x, lower_shadow_y);
    if lower_shadow_distance <= lower_shadow_radius && distance <= body_radius {
        let fade = 1.0 - lower_shadow_distance / lower_shadow_radius;
        color = color.over(LinearColor::rgba(0.0, 0.21, 0.19, 0.28 * fade));
    }

    if distance <= body_radius && distance >= body_radius - size * 0.014 {
        color = color.over(LinearColor::rgba(1.0, 1.0, 1.0, 0.28));
    }

    let highlight_x = center - body_radius * 0.33;
    let highlight_y = center - body_radius * 0.42;
    let highlight_rx = body_radius * 0.42;
    let highlight_ry = body_radius * 0.26;
    let highlight =
        ((x - highlight_x) / highlight_rx).powi(2) + ((y - highlight_y) / highlight_ry).powi(2);
    if highlight <= 1.0 && distance <= body_radius {
        color = color.over(LinearColor::rgba(1.0, 1.0, 1.0, (1.0 - highlight) * 0.16));
    }

    let inner_ring_radius = body_radius - size * 0.09;
    if distance <= inner_ring_radius && distance >= inner_ring_radius - size * 0.010 {
        color = color.over(LinearColor::rgba(1.0, 1.0, 1.0, 0.16));
    }

    if point_in_mark(size, x, y) {
        color = color.over(LinearColor::rgba(1.0, 1.0, 1.0, 0.95));
    }

    color.over(status_badge_color(size, x, y))
}

fn status_badge_color(size: f64, x: f64, y: f64) -> LinearColor {
    let center_x = size * STATUS_CENTER_X_RATIO;
    let center_y = size * STATUS_CENTER_Y_RATIO;
    let distance = point_distance(x, y, center_x, center_y);
    let fill_radius = size * STATUS_RADIUS_RATIO;
    let border_radius = size * STATUS_BORDER_RADIUS_RATIO;

    if distance <= fill_radius {
        return LinearColor::rgba(1.0, 0.82, 0.24, 1.0);
    }

    if distance <= border_radius {
        return LinearColor::rgba(0.00, 0.26, 0.24, 0.95);
    }

    let glow_radius = size * 0.16;
    if distance <= glow_radius {
        let fade = 1.0 - distance / glow_radius;
        return LinearColor::rgba(1.0, 0.78, 0.16, 0.20 * fade * fade);
    }

    LinearColor::default()
}

fn point_distance(x: f64, y: f64, center_x: f64, center_y: f64) -> f64 {
    let dx = x - center_x;
    let dy = y - center_y;
    (dx * dx + dy * dy).sqrt()
}

fn point_in_mark(size: f64, x: f64, y: f64) -> bool {
    let center = size / 2.0;
    let stem_half_width = size * MARK_HALF_WIDTH_RATIO;
    let stem_half_height = size * MARK_HALF_HEIGHT_RATIO;
    let cap_half_width = size * 0.07;
    let cap_half_height = size * 0.028;

    let in_stem = (x - center).abs() <= stem_half_width && (y - center).abs() <= stem_half_height;
    let in_top_cap = (x - center).abs() <= cap_half_width
        && (y - (center - stem_half_height)).abs() <= cap_half_height;
    let in_bottom_cap = (x - center).abs() <= cap_half_width
        && (y - (center + stem_half_height)).abs() <= cap_half_height;

    in_stem || in_top_cap || in_bottom_cap
}

#[derive(Clone, Copy, Default)]
struct LinearColor {
    red: f64,
    green: f64,
    blue: f64,
    alpha: f64,
}

impl LinearColor {
    fn rgba(red: f64, green: f64, blue: f64, alpha: f64) -> Self {
        Self {
            red: red * alpha,
            green: green * alpha,
            blue: blue * alpha,
            alpha,
        }
    }

    fn over(self, foreground: Self) -> Self {
        let remaining = 1.0 - foreground.alpha;
        Self {
            red: foreground.red + self.red * remaining,
            green: foreground.green + self.green * remaining,
            blue: foreground.blue + self.blue * remaining,
            alpha: foreground.alpha + self.alpha * remaining,
        }
    }

    fn scale(self, factor: f64) -> Self {
        Self {
            red: self.red * factor,
            green: self.green * factor,
            blue: self.blue * factor,
            alpha: self.alpha * factor,
        }
    }

    fn add(self, other: Self) -> Self {
        Self {
            red: self.red + other.red,
            green: self.green + other.green,
            blue: self.blue + other.blue,
            alpha: self.alpha + other.alpha,
        }
    }

    fn to_bgra_premultiplied(self) -> BgraPixel {
        BgraPixel {
            blue: unit_to_byte(self.blue),
            green: unit_to_byte(self.green),
            red: unit_to_byte(self.red),
            alpha: unit_to_byte(self.alpha),
        }
    }
}

fn unit_to_byte(value: f64) -> u8 {
    (value.clamp(0.0, 1.0) * 255.0).round() as u8
}

#[cfg(test)]
mod tests {
    use crate::geometry::point_in_circle;

    use super::{
        orb_bitmap_to_bgra_bytes, render_default_orb_bitmap, render_orb_bitmap, BgraPixel,
        OrbBitmap, ORB_BITMAP_SIZE,
    };

    #[test]
    fn default_orb_is_one_step_smaller_than_the_electron_spike() {
        let bitmap = render_default_orb_bitmap();

        assert_eq!(ORB_BITMAP_SIZE, 88);
        assert_eq!(bitmap.size, 88);
    }

    #[test]
    fn default_orb_uses_the_packaged_brand_asset_palette() {
        let bitmap = render_default_orb_bitmap();

        let center = bitmap.pixel(44, 44);
        assert!(center.red > 180);
        assert!(center.green < 90);
        assert!(center.blue < 90);
        assert_eq!(center.alpha, 255);
    }

    #[test]
    fn procedural_fallback_renders_transparent_corners_and_teal_center() {
        let bitmap = render_orb_bitmap(ORB_BITMAP_SIZE);

        assert_eq!(bitmap.pixel(0, 0).alpha, 0);
        assert_eq!(bitmap.pixel(87, 0).alpha, 0);

        let center = bitmap.pixel(44, 44);
        assert_eq!(center.alpha, 255);
        assert!(center.green > center.red);
        assert!(center.green > center.blue);
        assert!(center.red > 0);
    }

    #[test]
    fn renders_antialiased_circle_edge() {
        let bitmap = render_orb_bitmap(ORB_BITMAP_SIZE);

        let top_edge = bitmap.pixel(44, 4);
        assert!(top_edge.alpha > 0);
        assert!(top_edge.alpha < 255);
    }

    #[test]
    fn renders_status_badge_inside_the_window_region() {
        let bitmap = render_orb_bitmap(ORB_BITMAP_SIZE);

        let badge = bitmap.pixel(68, 68);
        assert!(badge.red > 180);
        assert!(badge.green > 150);
        assert!(badge.blue < 120);
        assert_eq!(badge.alpha, 255);

        let badge_outer_edge = bitmap.pixel(73, 73);
        assert!(badge_outer_edge.alpha > 200);
        assert!(point_in_circle(
            73,
            73,
            ORB_BITMAP_SIZE as i32,
            ORB_BITMAP_SIZE as i32
        ));
    }

    #[test]
    fn serializes_pixels_as_bgra_bytes_for_win32() {
        let bitmap = OrbBitmap {
            size: 1,
            pixels: vec![BgraPixel {
                blue: 3,
                green: 2,
                red: 1,
                alpha: 4,
            }],
        };
        let bytes = orb_bitmap_to_bgra_bytes(&bitmap);

        assert_eq!(bytes, vec![3, 2, 1, 4]);
    }
}
