# etcd2vector Sync Driver

Simple Rust sync driver for syncing data from etcd to Qdrant vector store.

## Project Structure

- `src/main.rs` - Entry point and sync logic
- `Cargo.toml` - Project manifest
- `.gitignore` - Git ignore rules

## Build

```bash
cargo build --release
```

## Run

```bash
cargo run
```

## Development

Check code:
```bash
cargo check
```

Run with logging:
```bash
RUST_LOG=debug cargo run
```
