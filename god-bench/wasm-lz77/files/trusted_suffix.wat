  (func $compress (param $data i32) (param $size i32) (param $out i32) (result i32)
    (local $pos i32) (local $out_len i32) (local $literal_start i32)
    (local $literal_len i32) (local $match i64) (local $length i32)
    (local $distance i32) (local $piece i32)
    (block $done
      (loop $scan
        local.get $pos
        local.get $size
        i32.ge_u
        br_if $done
        local.get $data
        local.get $size
        local.get $pos
        call $find_match
        local.tee $match
        i64.const 32
        i64.shr_u
        i32.wrap_i64
        local.set $length
        local.get $match
        i32.wrap_i64
        local.set $distance
        local.get $length
        i32.const 3
        i32.ge_u
        if
          (block $literals_done
            (loop $literals
              local.get $literal_len
              i32.eqz
              br_if $literals_done
              local.get $literal_len i32.const 128 i32.lt_u
              if (result i32) local.get $literal_len else i32.const 128 end
              local.set $piece
              local.get $out local.get $out_len i32.add
              local.get $piece i32.const 1 i32.sub i32.store8
              local.get $out local.get $out_len i32.add i32.const 1 i32.add
              local.get $data local.get $literal_start i32.add
              local.get $piece memory.copy
              local.get $out_len local.get $piece i32.const 1 i32.add i32.add local.set $out_len
              local.get $literal_start local.get $piece i32.add local.set $literal_start
              local.get $literal_len local.get $piece i32.sub local.set $literal_len
              br $literals))
          local.get $out local.get $out_len i32.add
          local.get $length i32.const 3 i32.sub i32.const 128 i32.or i32.store8
          local.get $out local.get $out_len i32.add i32.const 1 i32.add
          local.get $distance i32.const 1 i32.sub i32.store16
          local.get $out_len i32.const 3 i32.add local.set $out_len
          local.get $pos local.get $length i32.add local.set $pos
        else
          local.get $literal_len i32.eqz
          if local.get $pos local.set $literal_start end
          local.get $literal_len i32.const 1 i32.add local.set $literal_len
          local.get $pos i32.const 1 i32.add local.set $pos
          local.get $literal_len i32.const 128 i32.eq
          if
            local.get $out local.get $out_len i32.add i32.const 127 i32.store8
            local.get $out local.get $out_len i32.add i32.const 1 i32.add
            local.get $data local.get $literal_start i32.add
            i32.const 128 memory.copy
            local.get $out_len i32.const 129 i32.add local.set $out_len
            i32.const 0 local.set $literal_len
          end
        end
        br $scan))
    local.get $literal_len
    if
      local.get $out local.get $out_len i32.add
      local.get $literal_len i32.const 1 i32.sub i32.store8
      local.get $out local.get $out_len i32.add i32.const 1 i32.add
      local.get $data local.get $literal_start i32.add
      local.get $literal_len memory.copy
      local.get $out_len local.get $literal_len i32.const 1 i32.add i32.add local.set $out_len
    end
    local.get $out_len)

  (func $decompress (param $data i32) (param $size i32) (param $out i32) (result i32)
    (local $pos i32) (local $out_len i32) (local $control i32)
    (local $length i32) (local $distance i32) (local $i i32)
    (block $done
      (loop $token
        local.get $pos local.get $size i32.ge_u br_if $done
        local.get $data local.get $pos i32.add i32.load8_u local.set $control
        local.get $pos i32.const 1 i32.add local.set $pos
        local.get $control i32.const 128 i32.lt_u
        if
          local.get $control i32.const 1 i32.add local.set $length
          local.get $pos local.get $length i32.add local.get $size i32.gt_u
          if call $fail end
          local.get $out_len local.get $length i32.add i32.const 33554432 i32.gt_u
          if call $fail end
          local.get $out local.get $out_len i32.add
          local.get $data local.get $pos i32.add
          local.get $length memory.copy
          local.get $pos local.get $length i32.add local.set $pos
          local.get $out_len local.get $length i32.add local.set $out_len
        else
          local.get $pos i32.const 2 i32.add local.get $size i32.gt_u
          if call $fail end
          local.get $control i32.const 127 i32.and i32.const 3 i32.add local.set $length
          local.get $data local.get $pos i32.add i32.load16_u i32.const 1 i32.add local.set $distance
          local.get $pos i32.const 2 i32.add local.set $pos
          local.get $distance i32.const 32768 i32.gt_u
          local.get $distance local.get $out_len i32.gt_u i32.or
          if call $fail end
          local.get $out_len local.get $length i32.add i32.const 33554432 i32.gt_u
          if call $fail end
          i32.const 0 local.set $i
          (loop $copy
            local.get $i local.get $length i32.lt_u
            if
              local.get $out local.get $out_len i32.add local.get $i i32.add
              local.get $out local.get $out_len i32.add local.get $distance i32.sub
              local.get $i i32.add i32.load8_u i32.store8
              local.get $i i32.const 1 i32.add local.set $i
              br $copy
            end)
          local.get $out_len local.get $length i32.add local.set $out_len
        end
        br $token))
    local.get $out_len)

  (func (export "_start")
    (local $size i32) (local $result i32) (local $mode i32)
    i32.const 16 i32.const 32 call $args_get
    if call $fail end
    i32.const 20 i32.load i32.load8_u local.set $mode
    i32.const 65536 i32.const 8388609 call $read_all local.set $size
    local.get $mode i32.const 99 i32.eq
    if
      i32.const 65536 local.get $size i32.const 10485760 call $compress local.set $result
    else
      local.get $mode i32.const 100 i32.ne
      if call $fail end
      i32.const 65536 local.get $size i32.const 10485760 call $decompress local.set $result
    end
    i32.const 10485760 local.get $result call $write_all)
)
