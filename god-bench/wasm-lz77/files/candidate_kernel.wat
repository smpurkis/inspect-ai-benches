  ;; Return (length << 32) | distance. Return zero if no match of at least
  ;; three bytes exists.
  (func $find_match (param $data i32) (param $size i32) (param $pos i32) (result i64)
    ;; TODO: search distances 1..min(pos, 32768), compare at most 130 bytes,
    ;; retain only strictly longer matches so equal lengths keep the smallest
    ;; distance, and pack the selected pair into the i64 result.
    i64.const 0)
