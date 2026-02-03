/// Logger utility
pub struct Logger;

impl Logger {
    /// Log an info message
    pub fn info(message: &str) {
        println!("[INFO] {}", message);
    }
    
    /// Log a warning message
    pub fn warn(message: &str) {
        eprintln!("[WARN] {}", message);
    }
    
    /// Log an error message
    pub fn error(message: &str) {
        eprintln!("[ERROR] {}", message);
    }
}
