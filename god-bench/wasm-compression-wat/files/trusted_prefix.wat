(module
  (import "wasi_snapshot_preview1" "fd_read" (func $fd_read (param i32 i32 i32 i32) (result i32)))
  (import "wasi_snapshot_preview1" "fd_write" (func $fd_write (param i32 i32 i32 i32) (result i32)))
  (import "wasi_snapshot_preview1" "args_get" (func $args_get (param i32 i32) (result i32)))
  (import "wasi_snapshot_preview1" "proc_exit" (func $exit (param i32)))
  (memory (export "memory") 1050 9800)
  (func $fail i32.const 1 call $exit unreachable)

  (func $ensure_memory (param $end i32)
    (local $pages i32)
    local.get $end i32.const 65535 i32.add i32.const 16 i32.shr_u local.set $pages
    local.get $pages memory.size i32.gt_u
    if
      local.get $pages memory.size i32.sub memory.grow i32.const -1 i32.eq
      if call $fail end
    end)

  (func $read_all (param $dst i32) (param $cap i32) (result i32)
    (local $size i32) (local $n i32)
    (loop $again
      local.get $size local.get $cap i32.ge_u if call $fail end
      i32.const 0 local.get $dst local.get $size i32.add i32.store
      i32.const 4
      local.get $cap local.get $size i32.sub i32.const 65536 i32.lt_u
      if (result i32)
        local.get $cap local.get $size i32.sub
      else
        i32.const 65536
      end
      i32.store
      i32.const 0 i32.const 0 i32.const 1 i32.const 8 call $fd_read if call $fail end
      i32.const 8 i32.load local.tee $n i32.eqz if local.get $size return end
      local.get $size local.get $n i32.add local.set $size
      br $again)
    unreachable)

  (func $write_all (param $src i32) (param $len i32)
    (local $done i32) (local $n i32)
    (loop $again
      local.get $done local.get $len i32.eq if return end
      i32.const 0 local.get $src local.get $done i32.add i32.store
      i32.const 4 local.get $len local.get $done i32.sub i32.store
      i32.const 1 i32.const 0 i32.const 1 i32.const 8 call $fd_write if call $fail end
      i32.const 8 i32.load local.tee $n i32.eqz if call $fail end
      local.get $done local.get $n i32.add local.set $done
      br $again))

  (func $same_chunk (param $a i32) (param $b i32) (result i32)
    local.get $a i32.load local.get $b i32.load i32.eq
    local.get $a i32.load8_u offset=4 local.get $b i32.load8_u offset=4 i32.eq i32.and)

  (func $chunk_greater (param $a i32) (param $b i32) (result i32)
    (local $i i32) (local $x i32) (local $y i32)
    (block $equal
      (loop $byte
        local.get $i i32.const 5 i32.ge_u br_if $equal
        local.get $a local.get $i i32.add i32.load8_u local.set $x
        local.get $b local.get $i i32.add i32.load8_u local.set $y
        local.get $x local.get $y i32.ne
        if local.get $x local.get $y i32.gt_u return end
        local.get $i i32.const 1 i32.add local.set $i
        br $byte))
    i32.const 0)

  ;; Build reference-ordered dictionary entries at $dict. Hash slots contain
  ;; (source position + 1, frequency); sorted records contain (position, count).
  (func $build_dictionary (param $data i32) (param $size i32) (param $dict i32) (result i32)
    (local $i i32) (local $slot i32) (local $entry i32) (local $records i32)
    (local $table_size i32) (local $mask i32)
    (local $record_count i32) (local $j i32) (local $pos i32) (local $freq i32)
    (local $prev_pos i32) (local $prev_freq i32)
    i32.const 1024 local.set $table_size
    (loop $size_table
      local.get $table_size local.get $size i32.const 2 i32.mul i32.ge_u
      if
      else
        local.get $table_size i32.const 2 i32.mul local.set $table_size
        br $size_table
      end)
    local.get $table_size i32.const 1 i32.sub local.set $mask
    i32.const 104000000 local.get $table_size i32.const 8 i32.mul i32.add local.tee $records
    i32.const 524280 i32.add call $ensure_memory
    i32.const 104000000 i32.const 0 local.get $table_size i32.const 8 i32.mul memory.fill
    local.get $size i32.const 5 i32.gt_u
    if
      (block $scan_done
        (loop $scan
          local.get $i local.get $size i32.const 5 i32.sub i32.ge_u br_if $scan_done
          local.get $data local.get $i i32.add i32.load
          local.get $data local.get $i i32.add i32.load8_u offset=4
          i32.const 24 i32.shl i32.xor local.get $mask i32.and local.set $slot
          (block $found
            (loop $probe
              i32.const 104000000 local.get $slot i32.const 8 i32.mul i32.add local.set $entry
              local.get $entry i32.load i32.eqz
              if
                local.get $entry local.get $i i32.const 1 i32.add i32.store
                local.get $entry i32.const 1 i32.store offset=4
                br $found
              end
              local.get $data local.get $i i32.add
              local.get $data local.get $entry i32.load i32.const 1 i32.sub i32.add call $same_chunk
              if
                local.get $entry local.get $entry i32.load offset=4 i32.const 1 i32.add i32.store offset=4
                br $found
              end
              local.get $slot i32.const 1 i32.add local.get $mask i32.and local.set $slot
              br $probe))
          local.get $i i32.const 1 i32.add local.set $i
          br $scan))
    end
    i32.const 0 local.set $slot
    (block $slots_done
      (loop $slots
        local.get $slot local.get $table_size i32.ge_u br_if $slots_done
        i32.const 104000000 local.get $slot i32.const 8 i32.mul i32.add local.set $entry
        local.get $entry i32.load offset=4 local.tee $freq i32.const 3 i32.ge_u
        if
          local.get $entry i32.load i32.const 1 i32.sub local.set $pos
          ;; Once full, discard values no better than the current last entry.
          local.get $record_count i32.const 65535 i32.lt_u
          if (result i32)
            i32.const 1
          else
            local.get $records i32.const 524272 i32.add local.tee $entry i32.load local.set $prev_pos
            local.get $entry i32.load offset=4 local.set $prev_freq
            local.get $freq local.get $prev_freq i32.gt_u
            local.get $freq local.get $prev_freq i32.eq
            local.get $data local.get $pos i32.add
            local.get $data local.get $prev_pos i32.add call $chunk_greater i32.and i32.or
          end
          if
            local.get $record_count i32.const 65535 i32.lt_u
            if (result i32) local.get $record_count else i32.const 65534 end
            local.set $j
            (block $inserted
              (loop $shift
                local.get $j i32.eqz br_if $inserted
                local.get $records local.get $j i32.const 1 i32.sub i32.const 8 i32.mul i32.add
                local.tee $entry i32.load local.set $prev_pos
                local.get $entry i32.load offset=4 local.set $prev_freq
                local.get $freq local.get $prev_freq i32.gt_u
                local.get $freq local.get $prev_freq i32.eq
                local.get $data local.get $pos i32.add
                local.get $data local.get $prev_pos i32.add call $chunk_greater i32.and i32.or
                i32.eqz br_if $inserted
                local.get $records local.get $j i32.const 8 i32.mul i32.add local.get $prev_pos i32.store
                local.get $records local.get $j i32.const 8 i32.mul i32.add local.get $prev_freq i32.store offset=4
                local.get $j i32.const 1 i32.sub local.set $j
                br $shift))
            local.get $records local.get $j i32.const 8 i32.mul i32.add local.get $pos i32.store
            local.get $records local.get $j i32.const 8 i32.mul i32.add local.get $freq i32.store offset=4
            local.get $record_count i32.const 65535 i32.lt_u
            if local.get $record_count i32.const 1 i32.add local.set $record_count end
          end
        end
        local.get $slot i32.const 1 i32.add local.set $slot
        br $slots))
    i32.const 0 local.set $i
    (loop $copy
      local.get $i local.get $record_count i32.lt_u
      if
        local.get $dict local.get $i i32.const 5 i32.mul i32.add
        local.get $data local.get $records local.get $i i32.const 8 i32.mul i32.add i32.load i32.add
        i32.const 5 memory.copy
        local.get $i i32.const 1 i32.add local.set $i
        br $copy
      end)
    local.get $record_count)

  ;; Emit canonical payload commands and return the payload byte count.
