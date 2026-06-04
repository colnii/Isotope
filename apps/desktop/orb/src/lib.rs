pub mod asset;
pub mod geometry;
pub mod interaction;
pub mod native;
pub mod render;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum NativeOrbEvent {
    OpenMiniWindow,
}

pub type NativeOrbEventHandler = dyn Fn(NativeOrbEvent) + Send + 'static;

pub fn dispatch_left_click(handler: &dyn Fn(NativeOrbEvent)) {
    handler(NativeOrbEvent::OpenMiniWindow);
}

pub use native::run_native_orb;

#[cfg(test)]
mod tests {
    use std::sync::Mutex;

    use super::{dispatch_left_click, NativeOrbEvent};

    #[test]
    fn left_click_dispatches_open_mini_window_event() {
        let events = Mutex::new(Vec::new());

        dispatch_left_click(&|event| {
            events.lock().expect("events mutex poisoned").push(event);
        });

        assert_eq!(
            events.into_inner().expect("events mutex poisoned"),
            vec![NativeOrbEvent::OpenMiniWindow]
        );
    }
}
