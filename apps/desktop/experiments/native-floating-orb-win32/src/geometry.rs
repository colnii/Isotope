pub fn point_in_circle(x: i32, y: i32, width: i32, height: i32) -> bool {
    let radius = width.min(height) as f64 / 2.0;
    let center_x = width as f64 / 2.0;
    let center_y = height as f64 / 2.0;
    let dx = x as f64 - center_x;
    let dy = y as f64 - center_y;

    dx * dx + dy * dy <= radius * radius
}

#[cfg(test)]
mod tests {
    use super::point_in_circle;

    #[test]
    fn accepts_points_inside_the_orb_circle() {
        assert!(point_in_circle(48, 48, 96, 96));
        assert!(point_in_circle(48, 4, 96, 96));
    }

    #[test]
    fn rejects_points_outside_the_orb_circle() {
        assert!(!point_in_circle(0, 0, 96, 96));
        assert!(!point_in_circle(95, 95, 96, 96));
    }
}
