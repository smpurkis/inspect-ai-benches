  (func $load_uint (param $ptr i32) (param $width i32) (result i32)
    (local $i i32) (local $value i32)
    (loop $bytes
      local.get $i local.get $width i32.lt_u
      if
        local.get $value local.get $ptr local.get $i i32.add i32.load8_u
        local.get $i i32.const 8 i32.mul i32.shl i32.or local.set $value
        local.get $i i32.const 1 i32.add local.set $i
        br $bytes
      end)
    local.get $value)

  (func $compress (param $data i32) (param $size i32) (param $out i32) (result i32)
    (local $dict_count i32) (local $payload i32) (local $payload_len i32)
    local.get $out local.get $size i32.add i32.const 1048576 i32.add call $ensure_memory
    local.get $out i32.const 0x31585051 i32.store
    local.get $out i32.const 1 i32.store8 offset=4
    local.get $out i32.const 2 i32.store8 offset=5
    local.get $out i32.const 2 i32.store8 offset=6
    local.get $out local.get $size i64.extend_i32_u i64.store offset=7
    local.get $data local.get $size local.get $out i32.const 17 i32.add
    call $build_dictionary local.set $dict_count
    local.get $out local.get $dict_count i32.store16 offset=15
    local.get $out i32.const 17 i32.add
    local.get $dict_count i32.const 5 i32.mul i32.add local.set $payload
    local.get $data local.get $size local.get $out i32.const 17 i32.add
    local.get $dict_count local.get $payload call $encode_payload local.set $payload_len
    local.get $payload local.get $out i32.sub local.get $payload_len i32.add)

  (func $decompress (param $data i32) (param $size i32) (param $out i32) (result i32)
    (local $width i32) (local $original i32) (local $dict_count i32)
    (local $dict i32) (local $pos i32) (local $out_len i32)
    (local $command i32) (local $count i32) (local $bytes i32)
    (local $i i32) (local $index i32)
    local.get $size i32.const 16 i32.lt_u if call $fail end
    local.get $data i32.load i32.const 0x31585051 i32.ne if call $fail end
    local.get $data i32.load8_u offset=4 i32.const 1 i32.ne if call $fail end
    local.get $data i32.load8_u offset=5 i32.const 2 i32.ne if call $fail end
    local.get $data i32.load8_u offset=6 local.tee $width
    i32.const 1 i32.lt_u
    local.get $width i32.const 4 i32.gt_u i32.or if call $fail end
    local.get $data i64.load offset=7 i64.const 67108864 i64.gt_u if call $fail end
    local.get $data i64.load offset=7 i32.wrap_i64 local.set $original
    local.get $out local.get $original i32.add call $ensure_memory
    i32.const 15 local.get $width i32.add local.get $size i32.gt_u if call $fail end
    local.get $data i32.const 15 i32.add local.get $width call $load_uint local.set $dict_count
    local.get $data i32.const 15 i32.add local.get $width i32.add local.set $dict
    i32.const 15 local.get $width i32.add
    local.get $dict_count i32.const 5 i32.mul i32.add local.tee $pos
    local.get $size i32.gt_u if call $fail end
    (block $done
      (loop $commands
        local.get $pos local.get $size i32.ge_u br_if $done
        local.get $pos i32.const 2 i32.add local.get $size i32.gt_u if call $fail end
        local.get $data local.get $pos i32.add i32.load8_u local.set $command
        local.get $data local.get $pos i32.add i32.load8_u offset=1 local.tee $count
        i32.eqz if call $fail end
        local.get $pos i32.const 2 i32.add local.set $pos
        local.get $command i32.eqz
        if
          local.get $pos local.get $count i32.add local.get $size i32.gt_u if call $fail end
          local.get $out_len local.get $count i32.add local.get $original i32.gt_u if call $fail end
          local.get $out local.get $out_len i32.add
          local.get $data local.get $pos i32.add local.get $count memory.copy
          local.get $pos local.get $count i32.add local.set $pos
          local.get $out_len local.get $count i32.add local.set $out_len
        else
          local.get $command i32.const 1 i32.ne if call $fail end
          local.get $count local.get $width i32.mul local.set $bytes
          local.get $pos local.get $bytes i32.add local.get $size i32.gt_u if call $fail end
          i32.const 0 local.set $i
          (loop $tokens
            local.get $i local.get $count i32.lt_u
            if
              local.get $data local.get $pos i32.add
              local.get $i local.get $width i32.mul i32.add
              local.get $width call $load_uint local.tee $index
              local.get $dict_count i32.ge_u if call $fail end
              local.get $out_len i32.const 5 i32.add local.get $original i32.gt_u if call $fail end
              local.get $out local.get $out_len i32.add
              local.get $dict local.get $index i32.const 5 i32.mul i32.add i32.const 5 memory.copy
              local.get $out_len i32.const 5 i32.add local.set $out_len
              local.get $i i32.const 1 i32.add local.set $i
              br $tokens
            end)
          local.get $pos local.get $bytes i32.add local.set $pos
        end
        br $commands))
    local.get $out_len local.get $original i32.ne if call $fail end
    local.get $out_len)

  (func (export "_start")
    (local $mode i32) (local $size i32) (local $result i32) (local $cap i32)
    i32.const 16 i32.const 32 call $args_get if call $fail end
    i32.const 20 i32.load i32.load8_u local.set $mode
    local.get $mode i32.const 99 i32.eq
    if (result i32) i32.const 33554433 else i32.const 67108865 end local.set $cap
    i32.const 65536 local.get $cap call $read_all local.set $size
    local.get $mode i32.const 99 i32.eq
    if
      i32.const 65536 local.get $size i32.const 68157440 call $compress local.set $result
    else
      local.get $mode i32.const 100 i32.ne if call $fail end
      i32.const 65536 local.get $size i32.const 68157440 call $decompress local.set $result
    end
    i32.const 68157440 local.get $result call $write_all)
)
