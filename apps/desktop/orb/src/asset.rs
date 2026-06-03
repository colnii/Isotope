use std::io::Cursor;

use crate::{
    geometry::point_in_circle,
    render::{BgraPixel, OrbBitmap},
};

pub const DEFAULT_ORB_ASSET_BYTES: &[u8] = include_bytes!("../assets/orb-default.png");

#[derive(Debug)]
pub enum OrbAssetError {
    InvalidSize,
    Decode(png::DecodingError),
    UnsupportedColor(png::ColorType),
}

impl From<png::DecodingError> for OrbAssetError {
    fn from(error: png::DecodingError) -> Self {
        Self::Decode(error)
    }
}

#[derive(Clone, Copy)]
struct RgbaPixel {
    red: u8,
    green: u8,
    blue: u8,
    alpha: u8,
}

#[derive(Clone, Copy, Default)]
struct PremultipliedSample {
    red: f64,
    green: f64,
    blue: f64,
    alpha: f64,
}

pub fn render_default_orb_asset(size: u32) -> Result<OrbBitmap, OrbAssetError> {
    render_orb_asset_png(DEFAULT_ORB_ASSET_BYTES, size)
}

pub fn render_orb_asset_png(bytes: &[u8], size: u32) -> Result<OrbBitmap, OrbAssetError> {
    if size == 0 {
        return Err(OrbAssetError::InvalidSize);
    }

    let source = decode_png_rgba(bytes)?;
    let crop = content_crop_bounds(&source);
    let mut pixels = Vec::with_capacity((size * size) as usize);
    for y in 0..size {
        for x in 0..size {
            let mut pixel = sample_source_pixel(&source, &crop, x, y, size);
            if !point_in_circle(x as i32, y as i32, size as i32, size as i32) {
                pixel.alpha = 0;
                pixel.red = 0;
                pixel.green = 0;
                pixel.blue = 0;
            }
            pixels.push(pixel);
        }
    }

    Ok(OrbBitmap { size, pixels })
}

fn content_crop_bounds(source: &DecodedPng) -> CropBounds {
    let mut left = source.width;
    let mut top = source.height;
    let mut right = 0;
    let mut bottom = 0;

    for y in 0..source.height {
        for x in 0..source.width {
            if is_artwork_pixel(source.pixel(x, y)) {
                left = left.min(x);
                top = top.min(y);
                right = right.max(x);
                bottom = bottom.max(y);
            }
        }
    }

    if left > right || top > bottom {
        return CropBounds {
            left: 0,
            top: 0,
            size: source.width.min(source.height).max(1),
        };
    }

    let content_width = right - left + 1;
    let content_height = bottom - top + 1;
    let crop_size = content_width
        .max(content_height)
        .min(source.width)
        .min(source.height)
        .max(1);
    let center_x = (left + right + 1) as f64 / 2.0;
    let center_y = (top + bottom + 1) as f64 / 2.0;
    let max_left = source.width - crop_size;
    let max_top = source.height - crop_size;
    let crop_left = (center_x - crop_size as f64 / 2.0)
        .round()
        .clamp(0.0, max_left as f64) as u32;
    let crop_top = (center_y - crop_size as f64 / 2.0)
        .round()
        .clamp(0.0, max_top as f64) as u32;

    CropBounds {
        left: crop_left,
        top: crop_top,
        size: crop_size,
    }
}

fn is_artwork_pixel(pixel: RgbaPixel) -> bool {
    if pixel.alpha == 0 {
        return false;
    }

    if pixel.alpha < 255 {
        return true;
    }

    let max_channel = pixel.red.max(pixel.green).max(pixel.blue);
    let min_channel = pixel.red.min(pixel.green).min(pixel.blue);
    !(min_channel >= 235 && max_channel - min_channel <= 6)
}

fn decode_png_rgba(bytes: &[u8]) -> Result<DecodedPng, OrbAssetError> {
    let mut decoder = png::Decoder::new(Cursor::new(bytes));
    decoder.set_transformations(png::Transformations::EXPAND | png::Transformations::STRIP_16);
    let mut reader = decoder.read_info()?;
    let mut buffer = vec![0; reader.output_buffer_size()];
    let info = reader.next_frame(&mut buffer)?;
    let frame = &buffer[..info.buffer_size()];
    let pixels = match info.color_type {
        png::ColorType::Rgba => rgba_pixels_from_rgba(frame),
        png::ColorType::Rgb => rgba_pixels_from_rgb(frame),
        png::ColorType::GrayscaleAlpha => rgba_pixels_from_grayscale_alpha(frame),
        png::ColorType::Grayscale => rgba_pixels_from_grayscale(frame),
        color_type => return Err(OrbAssetError::UnsupportedColor(color_type)),
    };

    Ok(DecodedPng {
        width: info.width,
        height: info.height,
        pixels,
    })
}

fn rgba_pixels_from_rgba(bytes: &[u8]) -> Vec<RgbaPixel> {
    bytes
        .chunks_exact(4)
        .map(|chunk| RgbaPixel {
            red: chunk[0],
            green: chunk[1],
            blue: chunk[2],
            alpha: chunk[3],
        })
        .collect()
}

fn rgba_pixels_from_rgb(bytes: &[u8]) -> Vec<RgbaPixel> {
    bytes
        .chunks_exact(3)
        .map(|chunk| RgbaPixel {
            red: chunk[0],
            green: chunk[1],
            blue: chunk[2],
            alpha: 255,
        })
        .collect()
}

fn rgba_pixels_from_grayscale_alpha(bytes: &[u8]) -> Vec<RgbaPixel> {
    bytes
        .chunks_exact(2)
        .map(|chunk| RgbaPixel {
            red: chunk[0],
            green: chunk[0],
            blue: chunk[0],
            alpha: chunk[1],
        })
        .collect()
}

fn rgba_pixels_from_grayscale(bytes: &[u8]) -> Vec<RgbaPixel> {
    bytes
        .iter()
        .map(|value| RgbaPixel {
            red: *value,
            green: *value,
            blue: *value,
            alpha: 255,
        })
        .collect()
}

fn sample_source_pixel(
    source: &DecodedPng,
    crop: &CropBounds,
    output_x: u32,
    output_y: u32,
    output_size: u32,
) -> BgraPixel {
    let source_x = crop.left as f64 + map_output_center_to_source(output_x, output_size, crop.size);
    let source_y = crop.top as f64 + map_output_center_to_source(output_y, output_size, crop.size);
    let x0 = source_x.floor().clamp(0.0, (source.width - 1) as f64) as u32;
    let y0 = source_y.floor().clamp(0.0, (source.height - 1) as f64) as u32;
    let x1 = (x0 + 1).min(source.width - 1);
    let y1 = (y0 + 1).min(source.height - 1);
    let tx = source_x - x0 as f64;
    let ty = source_y - y0 as f64;

    let top = mix_sample(
        source.premultiplied_pixel(x0, y0),
        source.premultiplied_pixel(x1, y0),
        tx,
    );
    let bottom = mix_sample(
        source.premultiplied_pixel(x0, y1),
        source.premultiplied_pixel(x1, y1),
        tx,
    );
    mix_sample(top, bottom, ty).to_bgra()
}

fn map_output_center_to_source(output: u32, output_size: u32, source_size: u32) -> f64 {
    ((output as f64 + 0.5) * source_size as f64 / output_size as f64 - 0.5)
        .clamp(0.0, (source_size - 1) as f64)
}

fn mix_sample(
    first: PremultipliedSample,
    second: PremultipliedSample,
    amount: f64,
) -> PremultipliedSample {
    let remaining = 1.0 - amount;
    PremultipliedSample {
        red: first.red * remaining + second.red * amount,
        green: first.green * remaining + second.green * amount,
        blue: first.blue * remaining + second.blue * amount,
        alpha: first.alpha * remaining + second.alpha * amount,
    }
}

fn unit_to_byte(value: f64) -> u8 {
    (value.clamp(0.0, 1.0) * 255.0).round() as u8
}

struct DecodedPng {
    width: u32,
    height: u32,
    pixels: Vec<RgbaPixel>,
}

struct CropBounds {
    left: u32,
    top: u32,
    size: u32,
}

impl DecodedPng {
    fn pixel(&self, x: u32, y: u32) -> RgbaPixel {
        self.pixels[(y * self.width + x) as usize]
    }

    fn premultiplied_pixel(&self, x: u32, y: u32) -> PremultipliedSample {
        let pixel = self.pixel(x, y);
        let alpha = pixel.alpha as f64 / 255.0;
        PremultipliedSample {
            red: pixel.red as f64 / 255.0 * alpha,
            green: pixel.green as f64 / 255.0 * alpha,
            blue: pixel.blue as f64 / 255.0 * alpha,
            alpha,
        }
    }
}

impl PremultipliedSample {
    fn to_bgra(self) -> BgraPixel {
        BgraPixel {
            blue: unit_to_byte(self.blue),
            green: unit_to_byte(self.green),
            red: unit_to_byte(self.red),
            alpha: unit_to_byte(self.alpha),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::{render_default_orb_asset, render_orb_asset_png};

    #[test]
    fn loads_packaged_orb_asset_at_requested_size() {
        let bitmap = render_default_orb_asset(88).expect("asset should decode");

        assert_eq!(bitmap.size, 88);
        assert_eq!(bitmap.pixel(0, 0).alpha, 0);

        let center = bitmap.pixel(44, 44);
        assert!(center.red > 180);
        assert!(center.green < 90);
        assert!(center.blue < 90);
        assert_eq!(center.alpha, 255);
    }

    #[test]
    fn crops_packaged_asset_to_the_visible_orb_content() {
        let bitmap = render_default_orb_asset(88).expect("asset should decode");

        let left_middle = bitmap.pixel(5, 44);
        assert!(left_middle.alpha > 200);
        assert!(
            left_middle.red < 235 || left_middle.green < 235 || left_middle.blue < 235,
            "left edge should contain orb artwork, not checkerboard margin"
        );
    }

    #[test]
    fn rejects_zero_sized_output() {
        let error = render_orb_asset_png(&[], 0).expect_err("zero size should be rejected");

        assert!(matches!(error, super::OrbAssetError::InvalidSize));
    }
}
