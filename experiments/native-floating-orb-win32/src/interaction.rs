pub const DRAG_THRESHOLD_PX: i32 = 4;

pub fn moved_far_enough_to_drag(
    start_x: i32,
    start_y: i32,
    current_x: i32,
    current_y: i32,
) -> bool {
    let dx = current_x - start_x;
    let dy = current_y - start_y;
    dx * dx + dy * dy >= DRAG_THRESHOLD_PX * DRAG_THRESHOLD_PX
}

#[cfg(test)]
mod tests {
    use super::moved_far_enough_to_drag;

    #[test]
    fn keeps_small_pointer_motion_as_click_intent() {
        assert!(!moved_far_enough_to_drag(10, 10, 12, 11));
    }

    #[test]
    fn treats_threshold_pointer_motion_as_drag_intent() {
        assert!(moved_far_enough_to_drag(10, 10, 14, 10));
    }
}
