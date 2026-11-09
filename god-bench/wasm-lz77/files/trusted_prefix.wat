(module
  (import "wasi_snapshot_preview1" "fd_read"
    (func $fd_read (param i32 i32 i32 i32) (result i32)))
  (import "wasi_snapshot_preview1" "fd_write"
    (func $fd_write (param i32 i32 i32 i32) (result i32)))
  (import "wasi_snapshot_preview1" "args_get"
    (func $args_get (param i32 i32) (result i32)))
  (import "wasi_snapshot_preview1" "proc_exit" (func $exit (param i32)))
  (memory (export "memory") 704)

  ;; The trusted driver reserves 0..65535 for WASI scratch space.
  (func $fail
    i32.const 1
    call $exit
    unreachable)

  (func $read_all (param $dst i32) (param $cap i32) (result i32)
    (local $size i32) (local $n i32)
    (loop $again
      local.get $size
      local.get $cap
      i32.ge_u
      if call $fail end
      i32.const 0
      local.get $dst
      local.get $size
      i32.add
      i32.store
      i32.const 4
      local.get $cap
      local.get $size
      i32.sub
      i32.store
      i32.const 0
      i32.const 0
      i32.const 1
      i32.const 8
      call $fd_read
      if call $fail end
      i32.const 8
      i32.load
      local.tee $n
      i32.eqz
      if local.get $size return end
      local.get $size
      local.get $n
      i32.add
      local.set $size
      br $again)
    unreachable)

  (func $write_all (param $src i32) (param $len i32)
    (local $done i32) (local $n i32)
    (loop $again
      local.get $done
      local.get $len
      i32.eq
      if return end
      i32.const 0
      local.get $src
      local.get $done
      i32.add
      i32.store
      i32.const 4
      local.get $len
      local.get $done
      i32.sub
      i32.store
      i32.const 1
      i32.const 0
      i32.const 1
      i32.const 8
      call $fd_write
      if call $fail end
      i32.const 8
      i32.load
      local.tee $n
      i32.eqz
      if call $fail end
      local.get $done
      local.get $n
      i32.add
      local.set $done
      br $again))

  ;; Return (length << 32) | distance. Length is 0 when no match exists.
