(module
  ;; ===== WASI Imports =====
  (import "wasi_snapshot_preview1" "args_sizes_get"
    (func $args_sizes_get (param i32 i32) (result i32)))
  (import "wasi_snapshot_preview1" "args_get"
    (func $args_get (param i32 i32) (result i32)))
  (import "wasi_snapshot_preview1" "path_open"
    (func $path_open (param i32 i32 i32 i32 i32 i64 i64 i32 i32) (result i32)))
  (import "wasi_snapshot_preview1" "fd_read"
    (func $fd_read (param i32 i32 i32 i32) (result i32)))
  (import "wasi_snapshot_preview1" "fd_write"
    (func $fd_write (param i32 i32 i32 i32) (result i32)))
  (import "wasi_snapshot_preview1" "fd_close"
    (func $fd_close (param i32) (result i32)))
  (import "wasi_snapshot_preview1" "fd_filestat_get"
    (func $fd_filestat_get (param i32 i32) (result i32)))
  (import "wasi_snapshot_preview1" "proc_exit"
    (func $proc_exit (param i32)))

  ;; ===== Memory: 256 pages = 16MB =====
  (memory (export "memory") 256)

  ;; Memory layout:
  ;;   0x000000 scratch: iovec(8), filestat(64@0x40), nread(4@0x80), fd_out(4@0x84)
  ;;                     argc(4@0x88), argv_bufsz(4@0x8C)
  ;;   0x000100 arg_ptrs (64 bytes)
  ;;   0x000200 arg_buf  (3072 bytes)
  ;;   0x000E00 string constants
  ;;   0x010000 INPUT_BUF  (4 MB)
  ;;   0x410000 OUTPUT_BUF (4 MB)
  ;;   0x810000 HASH_TABLE (65536 entries * 16 bytes = 1 MB)
  ;;   0x910000 DICT_BUF   (65535 * 5 bytes ~ 320 KB)
  ;;   0x960000 CAND_BUF   (candidates, 8 bytes each)
  ;;   0x9E0000 TOK_BUF    (255 * 4 bytes)

  ;; ===== Data Segments =====
  (data (i32.const 0x0E00) "compress\00")
  (data (i32.const 0x0E10) "decompress\00")

  ;; ===== Globals =====
  (global $input_len  (mut i32) (i32.const 0))
  (global $output_len (mut i32) (i32.const 0))

  ;; ===== memcpy =====
  (func $memcpy (param $dst i32) (param $src i32) (param $len i32)
    (local $i i32)
    (local.set $i (i32.const 0))
    (block $brk
      (loop $lp
        (br_if $brk (i32.ge_u (local.get $i) (local.get $len)))
        (i32.store8
          (i32.add (local.get $dst) (local.get $i))
          (i32.load8_u (i32.add (local.get $src) (local.get $i))))
        (local.set $i (i32.add (local.get $i) (i32.const 1)))
        (br $lp))))

  ;; ===== memset =====
  (func $memset (param $dst i32) (param $val i32) (param $len i32)
    (local $i i32)
    (local $v32 i32)
    ;; Build 4-byte fill pattern
    (local.set $v32
      (i32.or
        (i32.or (local.get $val)
                (i32.shl (local.get $val) (i32.const 8)))
        (i32.or (i32.shl (local.get $val) (i32.const 16))
                (i32.shl (local.get $val) (i32.const 24)))))
    (local.set $i (i32.const 0))
    ;; Fast path: 4 bytes at a time
    (block $brk
      (loop $lp
        (br_if $brk (i32.gt_u (i32.add (local.get $i) (i32.const 4)) (local.get $len)))
        (i32.store (i32.add (local.get $dst) (local.get $i)) (local.get $v32))
        (local.set $i (i32.add (local.get $i) (i32.const 4)))
        (br $lp)))
    ;; Remainder
    (block $brk2
      (loop $lp2
        (br_if $brk2 (i32.ge_u (local.get $i) (local.get $len)))
        (i32.store8 (i32.add (local.get $dst) (local.get $i)) (local.get $val))
        (local.set $i (i32.add (local.get $i) (i32.const 1)))
        (br $lp2))))

  ;; ===== cmp5: compare 5 bytes, return 1 if equal =====
  (func $cmp5 (param $a i32) (param $b i32) (result i32)
    (if (i32.ne (i32.load (local.get $a)) (i32.load (local.get $b)))
      (then (return (i32.const 0))))
    (if (i32.ne (i32.load8_u (i32.add (local.get $a) (i32.const 4)))
                (i32.load8_u (i32.add (local.get $b) (i32.const 4))))
      (then (return (i32.const 0))))
    (i32.const 1))

  ;; ===== strlen (null-terminated) =====
  (func $strlen (param $ptr i32) (result i32)
    (local $n i32)
    (local.set $n (i32.const 0))
    (block $brk
      (loop $lp
        (br_if $brk (i32.eqz (i32.load8_u (i32.add (local.get $ptr) (local.get $n)))))
        (local.set $n (i32.add (local.get $n) (i32.const 1)))
        (br $lp)))
    (local.get $n))

  ;; ===== strcmp (null-terminated), 1=equal =====
  (func $strcmp (param $a i32) (param $b i32) (result i32)
    (local $i i32)
    (local.set $i (i32.const 0))
    (block $brk
      (loop $lp
        (if (i32.ne (i32.load8_u (i32.add (local.get $a) (local.get $i)))
                    (i32.load8_u (i32.add (local.get $b) (local.get $i))))
          (then (return (i32.const 0))))
        (if (i32.eqz (i32.load8_u (i32.add (local.get $a) (local.get $i))))
          (then (return (i32.const 1))))
        (local.set $i (i32.add (local.get $i) (i32.const 1)))
        (br $lp)))
    (unreachable))

  ;; ===== write_le: write val as width bytes little-endian =====
  (func $write_le (param $ptr i32) (param $val i32) (param $w i32)
    (i32.store8 (local.get $ptr) (local.get $val))
    (if (i32.ge_u (local.get $w) (i32.const 2))
      (then (i32.store8 (i32.add (local.get $ptr) (i32.const 1))
              (i32.shr_u (local.get $val) (i32.const 8)))))
    (if (i32.ge_u (local.get $w) (i32.const 3))
      (then (i32.store8 (i32.add (local.get $ptr) (i32.const 2))
              (i32.shr_u (local.get $val) (i32.const 16)))))
    (if (i32.ge_u (local.get $w) (i32.const 4))
      (then (i32.store8 (i32.add (local.get $ptr) (i32.const 3))
              (i32.shr_u (local.get $val) (i32.const 24))))))

  ;; ===== read_le: read width bytes little-endian =====
  (func $read_le (param $ptr i32) (param $w i32) (result i32)
    (local $v i32)
    (local.set $v (i32.load8_u (local.get $ptr)))
    (if (i32.ge_u (local.get $w) (i32.const 2))
      (then (local.set $v (i32.or (local.get $v)
              (i32.shl (i32.load8_u (i32.add (local.get $ptr) (i32.const 1)))
                       (i32.const 8))))))
    (if (i32.ge_u (local.get $w) (i32.const 3))
      (then (local.set $v (i32.or (local.get $v)
              (i32.shl (i32.load8_u (i32.add (local.get $ptr) (i32.const 2)))
                       (i32.const 16))))))
    (if (i32.ge_u (local.get $w) (i32.const 4))
      (then (local.set $v (i32.or (local.get $v)
              (i32.shl (i32.load8_u (i32.add (local.get $ptr) (i32.const 3)))
                       (i32.const 24))))))
    (local.get $v))

  ;; ================================================================
  ;; File I/O
  ;; ================================================================

  ;; read_file: read entire file into buf. Returns bytes read or -1.
  (func $read_file (param $path i32) (param $plen i32)
                   (param $buf i32) (param $max i32) (result i32)
    (local $fd i32) (local $err i32) (local $fsize i32)
    (local $total i32) (local $nr i32) (local $want i32)
    (local $ap i32) (local $al i32)

    ;; Strip leading '/'
    (local.set $ap (local.get $path))
    (local.set $al (local.get $plen))
    (if (i32.and (i32.gt_u (local.get $plen) (i32.const 0))
                 (i32.eq (i32.load8_u (local.get $path)) (i32.const 0x2F)))
      (then
        (local.set $ap (i32.add (local.get $path) (i32.const 1)))
        (local.set $al (i32.sub (local.get $plen) (i32.const 1)))))

    ;; path_open for reading
    (local.set $err
      (call $path_open
        (i32.const 3)        ;; dirfd
        (i32.const 1)        ;; SYMLINK_FOLLOW
        (local.get $ap) (local.get $al)
        (i32.const 0)        ;; oflags
        (i64.const 0x200026) ;; rights: FD_READ|FD_SEEK|FD_TELL|FD_FILESTAT_GET
        (i64.const 0)
        (i32.const 0)
        (i32.const 0x84)))    ;; -> fd
    (if (local.get $err) (then (return (i32.const -1))))
    (local.set $fd (i32.load (i32.const 0x84)))

    ;; fd_filestat_get  (buf at 0x40, 8-byte aligned; size at +32)
    (local.set $err (call $fd_filestat_get (local.get $fd) (i32.const 0x40)))
    (if (local.get $err) (then
      (drop (call $fd_close (local.get $fd))) (return (i32.const -1))))
    (local.set $fsize (i32.load (i32.const 0x60)))  ;; low 32 bits of size
    (if (i32.gt_u (local.get $fsize) (local.get $max))
      (then (local.set $fsize (local.get $max))))

    ;; Read loop
    (local.set $total (i32.const 0))
    (block $done
      (loop $rd
        (local.set $want (i32.sub (local.get $fsize) (local.get $total)))
        (br_if $done (i32.le_s (local.get $want) (i32.const 0)))
        ;; iovec at 0x00: {buf_ptr, buf_len}
        (i32.store (i32.const 0x00) (i32.add (local.get $buf) (local.get $total)))
        (i32.store (i32.const 0x04) (local.get $want))
        (local.set $err
          (call $fd_read (local.get $fd) (i32.const 0x00) (i32.const 1) (i32.const 0x80)))
        (if (local.get $err) (then
          (drop (call $fd_close (local.get $fd))) (return (i32.const -1))))
        (local.set $nr (i32.load (i32.const 0x80)))
        (br_if $done (i32.eqz (local.get $nr)))
        (local.set $total (i32.add (local.get $total) (local.get $nr)))
        (br $rd)))
    (drop (call $fd_close (local.get $fd)))
    (local.get $total))

  ;; write_file: write buf to file. Returns 0 on success, -1 on error.
  (func $write_file (param $path i32) (param $plen i32)
                    (param $buf i32) (param $len i32) (result i32)
    (local $fd i32) (local $err i32)
    (local $total i32) (local $nw i32)
    (local $ap i32) (local $al i32)

    (local.set $ap (local.get $path))
    (local.set $al (local.get $plen))
    (if (i32.and (i32.gt_u (local.get $plen) (i32.const 0))
                 (i32.eq (i32.load8_u (local.get $path)) (i32.const 0x2F)))
      (then
        (local.set $ap (i32.add (local.get $path) (i32.const 1)))
        (local.set $al (i32.sub (local.get $plen) (i32.const 1)))))

    ;; path_open for writing (CREAT|TRUNC = 9)
    (local.set $err
      (call $path_open
        (i32.const 3) (i32.const 1)
        (local.get $ap) (local.get $al)
        (i32.const 9)
        (i64.const 0x200066) ;; rights: FD_READ|FD_WRITE|FD_SEEK|FD_TELL|FD_FILESTAT_GET
        (i64.const 0)
        (i32.const 0)
        (i32.const 0x84)))
    (if (local.get $err) (then (return (i32.const -1))))
    (local.set $fd (i32.load (i32.const 0x84)))

    (local.set $total (i32.const 0))
    (block $done
      (loop $wr
        (br_if $done (i32.ge_u (local.get $total) (local.get $len)))
        (i32.store (i32.const 0x00) (i32.add (local.get $buf) (local.get $total)))
        (i32.store (i32.const 0x04) (i32.sub (local.get $len) (local.get $total)))
        (local.set $err
          (call $fd_write (local.get $fd) (i32.const 0x00) (i32.const 1) (i32.const 0x80)))
        (if (local.get $err) (then
          (drop (call $fd_close (local.get $fd))) (return (i32.const -1))))
        (local.set $nw (i32.load (i32.const 0x80)))
        (local.set $total (i32.add (local.get $total) (local.get $nw)))
        (br $wr)))
    (drop (call $fd_close (local.get $fd)))
    (i32.const 0))

  ;; ================================================================
  ;; Hash table (65536 entries, 16 bytes each)
  ;; Entry: [occupied:i32 +0] [key_4b:i32 +4] [key_5th:i32 +8] [count:i32 +12]
  ;; ================================================================

  (func $hash5 (param $p i32) (result i32)
    (local $h i32)
    (local.set $h (i32.load8_u (local.get $p)))
    (local.set $h (i32.add (i32.mul (local.get $h) (i32.const 31))
                           (i32.load8_u (i32.add (local.get $p) (i32.const 1)))))
    (local.set $h (i32.add (i32.mul (local.get $h) (i32.const 31))
                           (i32.load8_u (i32.add (local.get $p) (i32.const 2)))))
    (local.set $h (i32.add (i32.mul (local.get $h) (i32.const 31))
                           (i32.load8_u (i32.add (local.get $p) (i32.const 3)))))
    (local.set $h (i32.add (i32.mul (local.get $h) (i32.const 31))
                           (i32.load8_u (i32.add (local.get $p) (i32.const 4)))))
    (i32.and (local.get $h) (i32.const 0xFFFF)))

  (func $ht_clear
    (call $memset (i32.const 0x810000) (i32.const 0) (i32.const 1048576)))

  ;; Insert 5-byte key at $dp into hash table, or increment its count.
  (func $ht_inc (param $dp i32)
    (local $h i32) (local $probe i32) (local $ea i32)
    (local.set $h (call $hash5 (local.get $dp)))
    (local.set $probe (i32.const 0))
    (block $done
      (loop $lp
        (local.set $ea
          (i32.add (i32.const 0x810000)
            (i32.shl (i32.and (i32.add (local.get $h) (local.get $probe))
                              (i32.const 0xFFFF))
                     (i32.const 4))))  ;; * 16
        ;; Empty slot?
        (if (i32.eqz (i32.load (local.get $ea)))
          (then
            (i32.store (local.get $ea) (i32.const 1))
            ;; Copy 5 key bytes
            (i32.store8 (i32.add (local.get $ea) (i32.const 4))
              (i32.load8_u (local.get $dp)))
            (i32.store8 (i32.add (local.get $ea) (i32.const 5))
              (i32.load8_u (i32.add (local.get $dp) (i32.const 1))))
            (i32.store8 (i32.add (local.get $ea) (i32.const 6))
              (i32.load8_u (i32.add (local.get $dp) (i32.const 2))))
            (i32.store8 (i32.add (local.get $ea) (i32.const 7))
              (i32.load8_u (i32.add (local.get $dp) (i32.const 3))))
            (i32.store8 (i32.add (local.get $ea) (i32.const 8))
              (i32.load8_u (i32.add (local.get $dp) (i32.const 4))))
            (i32.store (i32.add (local.get $ea) (i32.const 12)) (i32.const 1))
            (br $done)))
        ;; Same key?
        (if (call $cmp5 (i32.add (local.get $ea) (i32.const 4)) (local.get $dp))
          (then
            (i32.store (i32.add (local.get $ea) (i32.const 12))
              (i32.add (i32.load (i32.add (local.get $ea) (i32.const 12)))
                       (i32.const 1)))
            (br $done)))
        ;; Probe next
        (local.set $probe (i32.add (local.get $probe) (i32.const 1)))
        (br $lp))))

  ;; ================================================================
  ;; build_dictionary
  ;; Stores entries at DICT_BUF (0x910000), 5 bytes each.
  ;; Returns dict_count.
  ;; ================================================================
  (func $build_dict (param $data i32) (param $dlen i32)
                    (param $maxd i32) (result i32)
    (local $i i32) (local $ea i32) (local $cnt i32) (local $sav i32)
    (local $ncand i32) (local $ca i32)
    (local $j i32) (local $best i32) (local $bsav i32)
    (local $ci i32) (local $cj i32)
    (local $ts i32) (local $ti i32) (local $dsz i32)

    (if (i32.lt_u (local.get $dlen) (i32.const 5))
      (then (return (i32.const 0))))

    (call $ht_clear)

    ;; Count all 5-byte windows
    (local.set $i (i32.const 0))
    (block $cd
      (loop $cl
        (br_if $cd (i32.gt_u (local.get $i)
                     (i32.sub (local.get $dlen) (i32.const 5))))
        (call $ht_inc (i32.add (local.get $data) (local.get $i)))
        (local.set $i (i32.add (local.get $i) (i32.const 1)))
        (br $cl)))

    ;; Build candidate list at CAND_BUF (0x960000)
    ;; Each candidate: [savings:i32, entry_addr:i32]
    (local.set $ncand (i32.const 0))
    (local.set $i (i32.const 0))
    (block $sd
      (loop $sl
        (br_if $sd (i32.ge_u (local.get $i) (i32.const 65536)))
        (local.set $ea (i32.add (i32.const 0x810000)
                         (i32.shl (local.get $i) (i32.const 4))))
        (if (i32.load (local.get $ea))
          (then
            (local.set $cnt (i32.load (i32.add (local.get $ea) (i32.const 12))))
            (if (i32.ge_u (local.get $cnt) (i32.const 3))
              (then
                (local.set $sav (i32.sub (i32.mul (local.get $cnt) (i32.const 4))
                                         (i32.const 5)))
                (if (i32.gt_s (local.get $sav) (i32.const 0))
                  (then
                    (local.set $ca (i32.add (i32.const 0x960000)
                                     (i32.shl (local.get $ncand) (i32.const 3))))
                    (i32.store (local.get $ca) (local.get $sav))
                    (i32.store (i32.add (local.get $ca) (i32.const 4)) (local.get $ea))
                    (local.set $ncand (i32.add (local.get $ncand) (i32.const 1)))))))))
        (local.set $i (i32.add (local.get $i) (i32.const 1)))
        (br $sl)))

    ;; Selection sort by savings descending
    (local.set $i (i32.const 0))
    (block $xd
      (loop $xl
        (br_if $xd (i32.ge_u (local.get $i) (local.get $ncand)))
        (local.set $ci (i32.add (i32.const 0x960000)
                         (i32.shl (local.get $i) (i32.const 3))))
        (local.set $best (local.get $i))
        (local.set $bsav (i32.load (local.get $ci)))
        ;; Inner loop
        (local.set $j (i32.add (local.get $i) (i32.const 1)))
        (block $id
          (loop $il
            (br_if $id (i32.ge_u (local.get $j) (local.get $ncand)))
            (local.set $cj (i32.add (i32.const 0x960000)
                             (i32.shl (local.get $j) (i32.const 3))))
            (if (i32.gt_s (i32.load (local.get $cj)) (local.get $bsav))
              (then
                (local.set $best (local.get $j))
                (local.set $bsav (i32.load (local.get $cj)))))
            (local.set $j (i32.add (local.get $j) (i32.const 1)))
            (br $il)))
        ;; Swap
        (if (i32.ne (local.get $best) (local.get $i))
          (then
            (local.set $ci (i32.add (i32.const 0x960000)
                             (i32.shl (local.get $i) (i32.const 3))))
            (local.set $cj (i32.add (i32.const 0x960000)
                             (i32.shl (local.get $best) (i32.const 3))))
            (local.set $ts (i32.load (local.get $ci)))
            (local.set $ti (i32.load (i32.add (local.get $ci) (i32.const 4))))
            (i32.store (local.get $ci) (i32.load (local.get $cj)))
            (i32.store (i32.add (local.get $ci) (i32.const 4))
              (i32.load (i32.add (local.get $cj) (i32.const 4))))
            (i32.store (local.get $cj) (local.get $ts))
            (i32.store (i32.add (local.get $cj) (i32.const 4)) (local.get $ti))))
        (local.set $i (i32.add (local.get $i) (i32.const 1)))
        (br $xl)))

    ;; Copy top min(ncand, maxd) to DICT_BUF (0x910000)
    (local.set $dsz
      (if (result i32) (i32.lt_u (local.get $ncand) (local.get $maxd))
        (then (local.get $ncand))
        (else (local.get $maxd))))
    (local.set $i (i32.const 0))
    (block $cpd
      (loop $cpl
        (br_if $cpd (i32.ge_u (local.get $i) (local.get $dsz)))
        (local.set $ca (i32.add (i32.const 0x960000)
                         (i32.shl (local.get $i) (i32.const 3))))
        (local.set $ea (i32.load (i32.add (local.get $ca) (i32.const 4))))
        (call $memcpy
          (i32.add (i32.const 0x910000) (i32.mul (local.get $i) (i32.const 5)))
          (i32.add (local.get $ea) (i32.const 4))
          (i32.const 5))
        (local.set $i (i32.add (local.get $i) (i32.const 1)))
        (br $cpl)))
    (local.get $dsz))

  ;; ================================================================
  ;; encode_payload
  ;; Writes encoded payload to $out. Returns bytes written.
  ;; ================================================================
  (func $encode_payload (param $data i32) (param $dlen i32)
                        (param $dict i32) (param $dcnt i32)
                        (param $dcb i32) (param $out i32) (result i32)
    (local $i i32) (local $op i32) (local $midx i32) (local $j i32) (local $de i32)
    (local $ls i32) (local $lc i32) (local $tc i32) (local $k i32) (local $piece i32)
    (local $idx i32)

    (local.set $op (i32.const 0))
    (local.set $i (i32.const 0))
    (local.set $lc (i32.const 0))
    (local.set $ls (i32.const 0))
    (local.set $tc (i32.const 0))

    (block $main_done
      (loop $main_lp
        (br_if $main_done (i32.ge_u (local.get $i) (local.get $dlen)))

        ;; Try dictionary match
        (local.set $midx (i32.const -1))
        (if (i32.le_u (i32.add (local.get $i) (i32.const 5)) (local.get $dlen))
          (then
            (local.set $j (i32.const 0))
            (block $md
              (loop $ml
                (br_if $md (i32.ge_u (local.get $j) (local.get $dcnt)))
                (local.set $de (i32.add (local.get $dict)
                                 (i32.mul (local.get $j) (i32.const 5))))
                (if (call $cmp5 (i32.add (local.get $data) (local.get $i))
                                (local.get $de))
                  (then
                    (local.set $midx (local.get $j))
                    (br $md)))
                (local.set $j (i32.add (local.get $j) (i32.const 1)))
                (br $ml)))))

        (if (i32.ne (local.get $midx) (i32.const -1))
          (then
            ;; === MATCH: flush pending literals ===
            (block $fl_done
              (loop $fl_lp
                (br_if $fl_done (i32.eqz (local.get $lc)))
                (local.set $piece
                  (if (result i32) (i32.gt_u (local.get $lc) (i32.const 255))
                    (then (i32.const 255)) (else (local.get $lc))))
                (i32.store8 (i32.add (local.get $out) (local.get $op)) (i32.const 0x00))
                (local.set $op (i32.add (local.get $op) (i32.const 1)))
                (i32.store8 (i32.add (local.get $out) (local.get $op)) (local.get $piece))
                (local.set $op (i32.add (local.get $op) (i32.const 1)))
                (call $memcpy
                  (i32.add (local.get $out) (local.get $op))
                  (i32.add (local.get $data) (local.get $ls))
                  (local.get $piece))
                (local.set $op (i32.add (local.get $op) (local.get $piece)))
                (local.set $ls (i32.add (local.get $ls) (local.get $piece)))
                (local.set $lc (i32.sub (local.get $lc) (local.get $piece)))
                (br $fl_lp)))

            ;; Add token
            (i32.store (i32.add (i32.const 0x9E0000)
                         (i32.shl (local.get $tc) (i32.const 2)))
              (local.get $midx))
            (local.set $tc (i32.add (local.get $tc) (i32.const 1)))

            ;; Flush tokens if full (255)
            (if (i32.eq (local.get $tc) (i32.const 255))
              (then
                (i32.store8 (i32.add (local.get $out) (local.get $op)) (i32.const 0x01))
                (local.set $op (i32.add (local.get $op) (i32.const 1)))
                (i32.store8 (i32.add (local.get $out) (local.get $op)) (local.get $tc))
                (local.set $op (i32.add (local.get $op) (i32.const 1)))
                (local.set $k (i32.const 0))
                (block $tw1d
                  (loop $tw1l
                    (br_if $tw1d (i32.ge_u (local.get $k) (local.get $tc)))
                    (local.set $idx
                      (i32.load (i32.add (i32.const 0x9E0000)
                                  (i32.shl (local.get $k) (i32.const 2)))))
                    (call $write_le
                      (i32.add (local.get $out) (local.get $op))
                      (local.get $idx) (local.get $dcb))
                    (local.set $op (i32.add (local.get $op) (local.get $dcb)))
                    (local.set $k (i32.add (local.get $k) (i32.const 1)))
                    (br $tw1l)))
                (local.set $tc (i32.const 0))))

            (local.set $i (i32.add (local.get $i) (i32.const 5))))

          (else
            ;; === NO MATCH: flush pending tokens ===
            (if (local.get $tc)
              (then
                (i32.store8 (i32.add (local.get $out) (local.get $op)) (i32.const 0x01))
                (local.set $op (i32.add (local.get $op) (i32.const 1)))
                (i32.store8 (i32.add (local.get $out) (local.get $op)) (local.get $tc))
                (local.set $op (i32.add (local.get $op) (i32.const 1)))
                (local.set $k (i32.const 0))
                (block $tw2d
                  (loop $tw2l
                    (br_if $tw2d (i32.ge_u (local.get $k) (local.get $tc)))
                    (local.set $idx
                      (i32.load (i32.add (i32.const 0x9E0000)
                                  (i32.shl (local.get $k) (i32.const 2)))))
                    (call $write_le
                      (i32.add (local.get $out) (local.get $op))
                      (local.get $idx) (local.get $dcb))
                    (local.set $op (i32.add (local.get $op) (local.get $dcb)))
                    (local.set $k (i32.add (local.get $k) (i32.const 1)))
                    (br $tw2l)))
                (local.set $tc (i32.const 0))))

            ;; Add literal
            (if (i32.eqz (local.get $lc))
              (then (local.set $ls (local.get $i))))
            (local.set $lc (i32.add (local.get $lc) (i32.const 1)))

            ;; Flush if 255
            (if (i32.eq (local.get $lc) (i32.const 255))
              (then
                (i32.store8 (i32.add (local.get $out) (local.get $op)) (i32.const 0x00))
                (local.set $op (i32.add (local.get $op) (i32.const 1)))
                (i32.store8 (i32.add (local.get $out) (local.get $op)) (i32.const 255))
                (local.set $op (i32.add (local.get $op) (i32.const 1)))
                (call $memcpy
                  (i32.add (local.get $out) (local.get $op))
                  (i32.add (local.get $data) (local.get $ls))
                  (i32.const 255))
                (local.set $op (i32.add (local.get $op) (i32.const 255)))
                (local.set $ls (i32.add (local.get $ls) (i32.const 255)))
                (local.set $lc (i32.const 0))))

            (local.set $i (i32.add (local.get $i) (i32.const 1)))))

        (br $main_lp)))

    ;; Flush remaining tokens
    (if (local.get $tc)
      (then
        (i32.store8 (i32.add (local.get $out) (local.get $op)) (i32.const 0x01))
        (local.set $op (i32.add (local.get $op) (i32.const 1)))
        (i32.store8 (i32.add (local.get $out) (local.get $op)) (local.get $tc))
        (local.set $op (i32.add (local.get $op) (i32.const 1)))
        (local.set $k (i32.const 0))
        (block $tw3d
          (loop $tw3l
            (br_if $tw3d (i32.ge_u (local.get $k) (local.get $tc)))
            (local.set $idx
              (i32.load (i32.add (i32.const 0x9E0000)
                          (i32.shl (local.get $k) (i32.const 2)))))
            (call $write_le
              (i32.add (local.get $out) (local.get $op))
              (local.get $idx) (local.get $dcb))
            (local.set $op (i32.add (local.get $op) (local.get $dcb)))
            (local.set $k (i32.add (local.get $k) (i32.const 1)))
            (br $tw3l)))))

    ;; Flush remaining literals
    (block $fl2d
      (loop $fl2l
        (br_if $fl2d (i32.eqz (local.get $lc)))
        (local.set $piece
          (if (result i32) (i32.gt_u (local.get $lc) (i32.const 255))
            (then (i32.const 255)) (else (local.get $lc))))
        (i32.store8 (i32.add (local.get $out) (local.get $op)) (i32.const 0x00))
        (local.set $op (i32.add (local.get $op) (i32.const 1)))
        (i32.store8 (i32.add (local.get $out) (local.get $op)) (local.get $piece))
        (local.set $op (i32.add (local.get $op) (i32.const 1)))
        (call $memcpy
          (i32.add (local.get $out) (local.get $op))
          (i32.add (local.get $data) (local.get $ls))
          (local.get $piece))
        (local.set $op (i32.add (local.get $op) (local.get $piece)))
        (local.set $ls (i32.add (local.get $ls) (local.get $piece)))
        (local.set $lc (i32.sub (local.get $lc) (local.get $piece)))
        (br $fl2l)))

    (local.get $op))

  ;; ================================================================
  ;; compress
  ;; Reads from $in (len $ilen), writes to $out. Returns output length.
  ;; ================================================================
  (func $compress (param $in i32) (param $ilen i32) (param $out i32) (result i32)
    (local $dc i32) (local $dcb i32) (local $maxd i32) (local $op i32)
    (local $plen i32) (local $i i32)

    (local.set $dcb (i32.const 2))
    (local.set $maxd (i32.const 65535))

    (local.set $dc (call $build_dict (local.get $in) (local.get $ilen) (local.get $maxd)))

    ;; Header (15 bytes): magic(4) ver(1) method(1) dcb(1) orig_size(8)
    (i32.store8 (local.get $out) (i32.const 0x51))                          ;; Q
    (i32.store8 (i32.add (local.get $out) (i32.const 1)) (i32.const 0x50))  ;; P
    (i32.store8 (i32.add (local.get $out) (i32.const 2)) (i32.const 0x58))  ;; X
    (i32.store8 (i32.add (local.get $out) (i32.const 3)) (i32.const 0x31))  ;; 1
    (i32.store8 (i32.add (local.get $out) (i32.const 4)) (i32.const 1))     ;; ver
    (i32.store8 (i32.add (local.get $out) (i32.const 5)) (i32.const 2))     ;; method
    (i32.store8 (i32.add (local.get $out) (i32.const 6)) (local.get $dcb))  ;; dcb
    ;; original_size as 64-bit LE (write low 32, then high 32 = 0)
    (i32.store (i32.add (local.get $out) (i32.const 7)) (local.get $ilen))
    (i32.store (i32.add (local.get $out) (i32.const 11)) (i32.const 0))
    (local.set $op (i32.const 15))

    ;; dict_count as dcb bytes LE
    (call $write_le (i32.add (local.get $out) (local.get $op))
                    (local.get $dc) (local.get $dcb))
    (local.set $op (i32.add (local.get $op) (local.get $dcb)))

    ;; Dictionary entries (5 bytes each)
    (local.set $i (i32.const 0))
    (block $dd
      (loop $dl
        (br_if $dd (i32.ge_u (local.get $i) (local.get $dc)))
        (call $memcpy
          (i32.add (local.get $out) (local.get $op))
          (i32.add (i32.const 0x910000) (i32.mul (local.get $i) (i32.const 5)))
          (i32.const 5))
        (local.set $op (i32.add (local.get $op) (i32.const 5)))
        (local.set $i (i32.add (local.get $i) (i32.const 1)))
        (br $dl)))

    ;; Payload (directly after dict in output)
    (local.set $plen
      (call $encode_payload
        (local.get $in) (local.get $ilen)
        (i32.const 0x910000) (local.get $dc)
        (local.get $dcb)
        (i32.add (local.get $out) (local.get $op))))
    (i32.add (local.get $op) (local.get $plen)))

  ;; ================================================================
  ;; decompress
  ;; Reads from $in (len $ilen), writes to $out. Returns output length.
  ;; ================================================================
  (func $decompress (param $in i32) (param $ilen i32) (param $out i32) (result i32)
    (local $dcb i32) (local $orig i32) (local $p i32)
    (local $dc i32) (local $dbytes i32) (local $dptr i32)
    (local $pp i32) (local $plen i32) (local $op i32)
    (local $cmd i32) (local $cnt i32) (local $idx i32) (local $cp i32)
    (local $i i32)

    ;; Check magic
    (if (i32.or
          (i32.or
            (i32.ne (i32.load8_u (local.get $in)) (i32.const 0x51))
            (i32.ne (i32.load8_u (i32.add (local.get $in) (i32.const 1))) (i32.const 0x50)))
          (i32.or
            (i32.ne (i32.load8_u (i32.add (local.get $in) (i32.const 2))) (i32.const 0x58))
            (i32.ne (i32.load8_u (i32.add (local.get $in) (i32.const 3))) (i32.const 0x31))))
      (then (call $proc_exit (i32.const 1)) (unreachable)))

    ;; Version must be 1
    (if (i32.ne (i32.load8_u (i32.add (local.get $in) (i32.const 4))) (i32.const 1))
      (then (call $proc_exit (i32.const 1)) (unreachable)))
    ;; Method must be 2
    (if (i32.ne (i32.load8_u (i32.add (local.get $in) (i32.const 5))) (i32.const 2))
      (then (call $proc_exit (i32.const 1)) (unreachable)))

    (local.set $dcb (i32.load8_u (i32.add (local.get $in) (i32.const 6))))
    (local.set $orig (i32.load (i32.add (local.get $in) (i32.const 7))))
    (local.set $p (i32.const 15))

    ;; dict_count
    (local.set $dc (call $read_le (i32.add (local.get $in) (local.get $p)) (local.get $dcb)))
    (local.set $p (i32.add (local.get $p) (local.get $dcb)))

    ;; Dictionary pointer (in-place in input)
    (local.set $dbytes (i32.mul (local.get $dc) (i32.const 5)))
    (local.set $dptr (i32.add (local.get $in) (local.get $p)))
    (local.set $p (i32.add (local.get $p) (local.get $dbytes)))

    ;; Payload
    (local.set $pp (i32.add (local.get $in) (local.get $p)))
    (local.set $plen (i32.sub (local.get $ilen) (local.get $p)))

    ;; Decode
    (local.set $op (i32.const 0))
    (local.set $p (i32.const 0))  ;; reuse as payload position
    (block $dec_done
      (loop $dec_lp
        (br_if $dec_done (i32.ge_u (local.get $p) (local.get $plen)))
        (local.set $cmd (i32.load8_u (i32.add (local.get $pp) (local.get $p))))
        (local.set $cnt (i32.load8_u (i32.add (local.get $pp)
                          (i32.add (local.get $p) (i32.const 1)))))
        (local.set $p (i32.add (local.get $p) (i32.const 2)))

        (if (i32.eq (local.get $cmd) (i32.const 0x00))
          (then
            ;; Literal block
            (call $memcpy
              (i32.add (local.get $out) (local.get $op))
              (i32.add (local.get $pp) (local.get $p))
              (local.get $cnt))
            (local.set $op (i32.add (local.get $op) (local.get $cnt)))
            (local.set $p (i32.add (local.get $p) (local.get $cnt))))
          (else
            (if (i32.eq (local.get $cmd) (i32.const 0x01))
              (then
                ;; Token block
                (local.set $i (i32.const 0))
                (block $td
                  (loop $tl
                    (br_if $td (i32.ge_u (local.get $i) (local.get $cnt)))
                    (local.set $idx
                      (call $read_le (i32.add (local.get $pp) (local.get $p))
                                     (local.get $dcb)))
                    (local.set $p (i32.add (local.get $p) (local.get $dcb)))
                    (local.set $cp
                      (i32.add (local.get $dptr)
                        (i32.mul (local.get $idx) (i32.const 5))))
                    (call $memcpy
                      (i32.add (local.get $out) (local.get $op))
                      (local.get $cp)
                      (i32.const 5))
                    (local.set $op (i32.add (local.get $op) (i32.const 5)))
                    (local.set $i (i32.add (local.get $i) (i32.const 1)))
                    (br $tl))))
              (else
                ;; Unknown command
                (call $proc_exit (i32.const 1))
                (unreachable)))))
        (br $dec_lp)))
    (local.get $op))

  ;; ================================================================
  ;; _start: entry point
  ;; ================================================================
  (func $_start (export "_start")
    (local $err i32)
    (local $mode_ptr i32) (local $inpath_ptr i32) (local $outpath_ptr i32)
    (local $mode_len i32) (local $inpath_len i32) (local $outpath_len i32)
    (local $is_compress i32)
    (local $in_len i32) (local $out_len i32)

    ;; Get args (expect 4: prog mode input output)
    (local.set $err (call $args_sizes_get (i32.const 0x88) (i32.const 0x8C)))
    (if (local.get $err)
      (then (call $proc_exit (i32.const 1)) (unreachable)))
    (if (i32.ne (i32.load (i32.const 0x88)) (i32.const 4))
      (then (call $proc_exit (i32.const 1)) (unreachable)))

    (local.set $err (call $args_get (i32.const 0x100) (i32.const 0x200)))
    (if (local.get $err)
      (then (call $proc_exit (i32.const 1)) (unreachable)))

    (local.set $mode_ptr   (i32.load (i32.const 0x104)))
    (local.set $inpath_ptr (i32.load (i32.const 0x108)))
    (local.set $outpath_ptr (i32.load (i32.const 0x10C)))

    (local.set $mode_len   (call $strlen (local.get $mode_ptr)))
    (local.set $inpath_len (call $strlen (local.get $inpath_ptr)))
    (local.set $outpath_len (call $strlen (local.get $outpath_ptr)))

    (local.set $is_compress (call $strcmp (local.get $mode_ptr) (i32.const 0x0E00)))

    ;; Read input file
    (local.set $in_len
      (call $read_file
        (local.get $inpath_ptr) (local.get $inpath_len)
        (i32.const 0x010000) (i32.const 0x400000)))
    (if (i32.eq (local.get $in_len) (i32.const -1))
      (then (call $proc_exit (i32.const 1)) (unreachable)))

    (if (local.get $is_compress)
      (then
        (local.set $out_len
          (call $compress
            (i32.const 0x010000) (local.get $in_len) (i32.const 0x410000))))
      (else
        (local.set $out_len
          (call $decompress
            (i32.const 0x010000) (local.get $in_len) (i32.const 0x410000)))))

    ;; Write output file
    (local.set $err
      (call $write_file
        (local.get $outpath_ptr) (local.get $outpath_len)
        (i32.const 0x410000) (local.get $out_len)))
    (if (local.get $err)
      (then (call $proc_exit (i32.const 1)) (unreachable)))

    (call $proc_exit (i32.const 0))
    (unreachable))
)
