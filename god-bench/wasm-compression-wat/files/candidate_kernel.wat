  ;; Emit payload commands at $out and return their total byte count.
  (func $encode_payload
    (param $data i32) (param $size i32) (param $dict i32)
    (param $dict_count i32) (param $out i32) (result i32)
    (local $pos i32) (local $out_len i32) (local $piece i32)
    ;; Starter behavior emits valid literal-only QPX1. Replace this with
    ;; left-to-right dictionary selection and canonical kind coalescing.
    (block $done
      (loop $blocks
        local.get $pos local.get $size i32.ge_u br_if $done
        local.get $size local.get $pos i32.sub i32.const 255 i32.lt_u
        if (result i32)
          local.get $size local.get $pos i32.sub
        else
          i32.const 255
        end
        local.set $piece
        local.get $out local.get $out_len i32.add i32.const 0 i32.store8
        local.get $out local.get $out_len i32.add local.get $piece i32.store8 offset=1
        local.get $out local.get $out_len i32.add i32.const 2 i32.add
        local.get $data local.get $pos i32.add local.get $piece memory.copy
        local.get $out_len local.get $piece i32.const 2 i32.add i32.add local.set $out_len
        local.get $pos local.get $piece i32.add local.set $pos
        br $blocks))
    local.get $out_len)
