//! Abandoned typed-IR backend from the November 2025 optimizer branch.
//!
//! This fragment is buildable only with its missing arena and encoder crates.
//! It remains useful for data-flow and structured-control ideas. Its f32 value
//! model, eager logic, preview0 ABI, and output-folding pass are incompatible
//! with the later release contract.

use std::collections::{BTreeMap, BTreeSet, VecDeque};

pub type BlockId = u32;
pub type ValueId = u32;
pub type FunctionId = u32;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ScalarType {
    F32,
    I32,
    TextPair,
    Unit,
}

#[derive(Clone, Debug)]
pub enum Instruction {
    ConstantF32 { dst: ValueId, bits: u32 },
    ConstantI32 { dst: ValueId, value: i32 },
    StaticText { dst: ValueId, offset: u32, length: u32 },
    AddF32 { dst: ValueId, left: ValueId, right: ValueId },
    SubF32 { dst: ValueId, left: ValueId, right: ValueId },
    MulF32 { dst: ValueId, left: ValueId, right: ValueId },
    DivF32 { dst: ValueId, left: ValueId, right: ValueId },
    RemHelper { dst: ValueId, left: ValueId, right: ValueId },
    Compare { dst: ValueId, op: CompareOp, left: ValueId, right: ValueId },
    BooleanAnd { dst: ValueId, left: ValueId, right: ValueId },
    BooleanOr { dst: ValueId, left: ValueId, right: ValueId },
    Call { dst: Option<ValueId>, function: FunctionId, arguments: Vec<ValueId> },
    JoinText { dst: ValueId, fragments: Vec<ValueId> },
    Print { value: ValueId },
}

#[derive(Clone, Copy, Debug)]
pub enum CompareOp {
    Equal,
    NotEqual,
    Less,
    LessEqual,
    Greater,
    GreaterEqual,
}

#[derive(Clone, Debug)]
pub enum Terminator {
    Jump(BlockId),
    Branch { condition: ValueId, yes: BlockId, no: BlockId },
    Return(Option<ValueId>),
    Exit(i32),
    Unreachable,
}

#[derive(Clone, Debug)]
pub struct Block {
    pub id: BlockId,
    pub instructions: Vec<Instruction>,
    pub terminator: Terminator,
}

#[derive(Clone, Debug)]
pub struct Function {
    pub id: FunctionId,
    pub name: String,
    pub parameters: Vec<(ValueId, ScalarType)>,
    pub result: ScalarType,
    pub entry: BlockId,
    pub blocks: BTreeMap<BlockId, Block>,
}

#[derive(Clone, Debug, Default)]
pub struct Module {
    pub functions: BTreeMap<FunctionId, Function>,
    pub names: BTreeMap<String, FunctionId>,
    pub data: Vec<u8>,
    pub entry: Option<FunctionId>,
}

impl Module {
    pub fn reachable_blocks(&self, function: FunctionId) -> BTreeSet<BlockId> {
        let body = &self.functions[&function];
        let mut work = VecDeque::from([body.entry]);
        let mut seen = BTreeSet::new();
        while let Some(id) = work.pop_front() {
            if !seen.insert(id) {
                continue;
            }
            match &body.blocks[&id].terminator {
                Terminator::Jump(next) => work.push_back(*next),
                Terminator::Branch { yes, no, .. } => {
                    work.push_back(*yes);
                    work.push_back(*no);
                }
                Terminator::Return(_) | Terminator::Exit(_) | Terminator::Unreachable => {}
            }
        }
        seen
    }

    pub fn reachable_functions(&self) -> BTreeSet<FunctionId> {
        let mut work = VecDeque::new();
        let mut seen = BTreeSet::new();
        if let Some(entry) = self.entry {
            work.push_back(entry);
        }
        while let Some(id) = work.pop_front() {
            if !seen.insert(id) {
                continue;
            }
            let function = &self.functions[&id];
            for block_id in self.reachable_blocks(id) {
                for instruction in &function.blocks[&block_id].instructions {
                    if let Instruction::Call { function: target, .. } = instruction {
                        work.push_back(*target);
                    }
                }
            }
        }
        seen
    }

    pub fn intern_text(&mut self, text: &str) -> (u32, u32) {
        if let Some(offset) = find_subslice(&self.data, text.as_bytes()) {
            return (offset as u32, text.len() as u32);
        }
        let offset = self.data.len() as u32;
        self.data.extend_from_slice(text.as_bytes());
        (offset, text.len() as u32)
    }
}

fn find_subslice(haystack: &[u8], needle: &[u8]) -> Option<usize> {
    if needle.is_empty() {
        return Some(0);
    }
    haystack.windows(needle.len()).position(|window| window == needle)
}

pub struct Builder {
    module: Module,
    current_function: FunctionId,
    current_block: BlockId,
    next_function: FunctionId,
    next_block: BlockId,
    next_value: ValueId,
    locals: Vec<BTreeMap<String, ValueId>>,
    loop_stack: Vec<(BlockId, BlockId)>,
}

impl Builder {
    pub fn new() -> Self {
        Self {
            module: Module::default(),
            current_function: 0,
            current_block: 0,
            next_function: 0,
            next_block: 0,
            next_value: 0,
            locals: Vec::new(),
            loop_stack: Vec::new(),
        }
    }

    fn value(&mut self) -> ValueId {
        let result = self.next_value;
        self.next_value += 1;
        result
    }

    fn block(&mut self) -> BlockId {
        let result = self.next_block;
        self.next_block += 1;
        result
    }

    fn append(&mut self, instruction: Instruction) {
        self.module.functions.get_mut(&self.current_function).unwrap()
            .blocks.get_mut(&self.current_block).unwrap()
            .instructions.push(instruction);
    }

    fn terminate(&mut self, terminator: Terminator) {
        self.module.functions.get_mut(&self.current_function).unwrap()
            .blocks.get_mut(&self.current_block).unwrap()
            .terminator = terminator;
    }

    pub fn lower_binary(&mut self, op: OldBinary, left: ValueId, right: ValueId) -> ValueId {
        let dst = self.value();
        let instruction = match op {
            OldBinary::Add => Instruction::AddF32 { dst, left, right },
            OldBinary::Subtract => Instruction::SubF32 { dst, left, right },
            OldBinary::Multiply => Instruction::MulF32 { dst, left, right },
            OldBinary::Divide => Instruction::DivF32 { dst, left, right },
            OldBinary::Remainder => Instruction::RemHelper { dst, left, right },
            OldBinary::Equal => Instruction::Compare { dst, op: CompareOp::Equal, left, right },
            OldBinary::NotEqual => Instruction::Compare { dst, op: CompareOp::NotEqual, left, right },
            OldBinary::Less => Instruction::Compare { dst, op: CompareOp::Less, left, right },
            OldBinary::LessEqual => Instruction::Compare { dst, op: CompareOp::LessEqual, left, right },
            OldBinary::Greater => Instruction::Compare { dst, op: CompareOp::Greater, left, right },
            OldBinary::GreaterEqual => Instruction::Compare { dst, op: CompareOp::GreaterEqual, left, right },
            // This old IR made eager evaluation unavoidable: both ValueIds have
            // already been produced by the time this method is called.
            OldBinary::And => Instruction::BooleanAnd { dst, left, right },
            OldBinary::Or => Instruction::BooleanOr { dst, left, right },
        };
        self.append(instruction);
        dst
    }

    pub fn lower_if(&mut self, condition: ValueId, then_body: impl FnOnce(&mut Self), else_body: impl FnOnce(&mut Self)) {
        let then_block = self.block();
        let else_block = self.block();
        let merge_block = self.block();
        self.insert_empty_block(then_block);
        self.insert_empty_block(else_block);
        self.insert_empty_block(merge_block);
        self.terminate(Terminator::Branch { condition, yes: then_block, no: else_block });

        self.current_block = then_block;
        self.locals.push(BTreeMap::new());
        then_body(self);
        self.locals.pop();
        if self.block_is_open(then_block) {
            self.terminate(Terminator::Jump(merge_block));
        }

        self.current_block = else_block;
        self.locals.push(BTreeMap::new());
        else_body(self);
        self.locals.pop();
        if self.block_is_open(else_block) {
            self.terminate(Terminator::Jump(merge_block));
        }
        self.current_block = merge_block;
    }

    pub fn lower_loop(&mut self, body: impl FnOnce(&mut Self)) {
        let header = self.block();
        let loop_body = self.block();
        let after = self.block();
        self.insert_empty_block(header);
        self.insert_empty_block(loop_body);
        self.insert_empty_block(after);
        self.terminate(Terminator::Jump(header));

        self.current_block = header;
        self.terminate(Terminator::Jump(loop_body));
        self.current_block = loop_body;
        self.loop_stack.push((header, after));
        self.locals.push(BTreeMap::new());
        body(self);
        self.locals.pop();
        self.loop_stack.pop();
        if self.block_is_open(loop_body) {
            self.terminate(Terminator::Jump(header));
        }
        self.current_block = after;
    }

    fn insert_empty_block(&mut self, id: BlockId) {
        self.module.functions.get_mut(&self.current_function).unwrap().blocks.insert(
            id,
            Block { id, instructions: Vec::new(), terminator: Terminator::Unreachable },
        );
    }

    fn block_is_open(&self, id: BlockId) -> bool {
        matches!(self.module.functions[&self.current_function].blocks[&id].terminator,
                 Terminator::Unreachable)
    }
}

#[derive(Clone, Copy)]
pub enum OldBinary {
    Add,
    Subtract,
    Multiply,
    Divide,
    Remainder,
    Equal,
    NotEqual,
    Less,
    LessEqual,
    Greater,
    GreaterEqual,
    And,
    Or,
}

pub mod passes {
    use super::*;

    #[derive(Clone, Debug)]
    enum Constant {
        F32(f32),
        I32(i32),
        Text(String),
    }

    /// Historical sparse constant propagation. Notice that f32 host
    /// arithmetic is used, so keeping this pass unchanged would alter values.
    pub fn propagate(function: &mut Function) {
        let mut known = BTreeMap::<ValueId, Constant>::new();
        for block in function.blocks.values_mut() {
            for instruction in &mut block.instructions {
                match instruction.clone() {
                    Instruction::ConstantF32 { dst, bits } => {
                        known.insert(dst, Constant::F32(f32::from_bits(bits)));
                    }
                    Instruction::ConstantI32 { dst, value } => {
                        known.insert(dst, Constant::I32(value));
                    }
                    Instruction::AddF32 { dst, left, right } => {
                        if let (Some(Constant::F32(a)), Some(Constant::F32(b))) =
                            (known.get(&left), known.get(&right))
                        {
                            let value = *a + *b;
                            *instruction = Instruction::ConstantF32 { dst, bits: value.to_bits() };
                            known.insert(dst, Constant::F32(value));
                        }
                    }
                    Instruction::SubF32 { dst, left, right } => {
                        if let (Some(Constant::F32(a)), Some(Constant::F32(b))) =
                            (known.get(&left), known.get(&right))
                        {
                            let value = *a - *b;
                            *instruction = Instruction::ConstantF32 { dst, bits: value.to_bits() };
                            known.insert(dst, Constant::F32(value));
                        }
                    }
                    Instruction::MulF32 { dst, left, right } => {
                        if let (Some(Constant::F32(a)), Some(Constant::F32(b))) =
                            (known.get(&left), known.get(&right))
                        {
                            let value = *a * *b;
                            *instruction = Instruction::ConstantF32 { dst, bits: value.to_bits() };
                            known.insert(dst, Constant::F32(value));
                        }
                    }
                    Instruction::DivF32 { dst, left, right } => {
                        if let (Some(Constant::F32(a)), Some(Constant::F32(b))) =
                            (known.get(&left), known.get(&right))
                        {
                            let value = *a / *b;
                            *instruction = Instruction::ConstantF32 { dst, bits: value.to_bits() };
                            known.insert(dst, Constant::F32(value));
                        }
                    }
                    _ => {}
                }
            }
        }
    }

    /// Rejected whole-program output folder. This pass interpreted reachable
    /// code and replaced Print nodes with static text. It is included to make
    /// archived review references intelligible, not as an implementation plan.
    pub fn fold_prints(module: &mut Module) -> Result<(), String> {
        let entry = module.entry.ok_or("entry missing")?;
        let mut evaluator = Evaluator::new(module);
        let output = evaluator.run(entry)?;
        let (offset, length) = module.intern_text(&output);
        let function = module.functions.get_mut(&entry).unwrap();
        function.blocks.clear();
        function.entry = 0;
        function.blocks.insert(0, Block {
            id: 0,
            instructions: vec![
                Instruction::StaticText { dst: 0, offset, length },
                Instruction::Print { value: 0 },
            ],
            terminator: Terminator::Return(None),
        });
        Ok(())
    }

    struct Evaluator<'a> {
        module: &'a Module,
        values: BTreeMap<ValueId, Constant>,
        output: String,
        fuel: usize,
    }

    impl<'a> Evaluator<'a> {
        fn new(module: &'a Module) -> Self {
            Self { module, values: BTreeMap::new(), output: String::new(), fuel: 100_000 }
        }

        fn run(&mut self, function: FunctionId) -> Result<String, String> {
            let body = &self.module.functions[&function];
            let mut block = body.entry;
            loop {
                self.fuel = self.fuel.checked_sub(1).ok_or("folding fuel exhausted")?;
                let current = &body.blocks[&block];
                for instruction in &current.instructions {
                    self.execute(instruction)?;
                }
                match current.terminator {
                    Terminator::Jump(next) => block = next,
                    Terminator::Branch { condition, yes, no } => {
                        block = match self.values.get(&condition) {
                            Some(Constant::I32(0)) => no,
                            Some(Constant::I32(_)) => yes,
                            _ => return Err("nonconstant branch".into()),
                        };
                    }
                    Terminator::Return(_) => return Ok(self.output.clone()),
                    Terminator::Exit(code) => return Err(format!("program exits {code}")),
                    Terminator::Unreachable => return Err("open block".into()),
                }
            }
        }

        fn execute(&mut self, instruction: &Instruction) -> Result<(), String> {
            match instruction {
                Instruction::ConstantF32 { dst, bits } => {
                    self.values.insert(*dst, Constant::F32(f32::from_bits(*bits)));
                }
                Instruction::ConstantI32 { dst, value } => {
                    self.values.insert(*dst, Constant::I32(*value));
                }
                Instruction::StaticText { dst, offset, length } => {
                    let start = *offset as usize;
                    let end = start + *length as usize;
                    let text = std::str::from_utf8(&self.module.data[start..end])
                        .map_err(|_| "bad static utf8")?;
                    self.values.insert(*dst, Constant::Text(text.to_owned()));
                }
                Instruction::Print { value } => {
                    match self.values.get(value) {
                        Some(Constant::Text(text)) => self.output.push_str(text),
                        Some(Constant::F32(number)) => self.output.push_str(&number.to_string()),
                        Some(Constant::I32(integer)) => self.output.push_str(&integer.to_string()),
                        None => return Err("dynamic print".into()),
                    }
                    self.output.push('\n');
                }
                _ => return Err("dynamic instruction".into()),
            }
            Ok(())
        }
    }
}

pub mod old_wat_emitter {
    use super::*;

    pub fn emit(module: &Module) -> String {
        let mut out = String::from("(module\n");
        out.push_str("  (import \"wasi_unstable\" \"fd_write\" ");
        out.push_str("(func $fd_write (param i32 i32 i32 i32) (result i32)))\n");
        out.push_str("  (import \"wasi_unstable\" \"proc_exit\" ");
        out.push_str("(func $proc_exit (param i32)))\n");
        out.push_str("  (memory (export \"memory\") 2)\n");
        for function in module.functions.values() {
            emit_function(&mut out, function);
        }
        if let Some(entry) = module.entry {
            out.push_str(&format!("  (export \"main\" (func $f{entry}))\n"));
        }
        emit_data(&mut out, &module.data);
        out.push_str(")\n");
        out
    }

    fn emit_function(out: &mut String, function: &Function) {
        out.push_str(&format!("  (func $f{}\n", function.id));
        for block in function.blocks.values() {
            out.push_str(&format!("    ;; block {}\n", block.id));
            for instruction in &block.instructions {
                emit_instruction(out, instruction);
            }
        }
        out.push_str("  )\n");
    }

    fn emit_instruction(out: &mut String, instruction: &Instruction) {
        match instruction {
            Instruction::ConstantF32 { bits, .. } => {
                out.push_str(&format!("    f32.const {}\n", f32::from_bits(*bits)));
            }
            Instruction::ConstantI32 { value, .. } => {
                out.push_str(&format!("    i32.const {value}\n"));
            }
            Instruction::AddF32 { .. } => out.push_str("    f32.add\n"),
            Instruction::SubF32 { .. } => out.push_str("    f32.sub\n"),
            Instruction::MulF32 { .. } => out.push_str("    f32.mul\n"),
            Instruction::DivF32 { .. } => out.push_str("    f32.div\n"),
            Instruction::BooleanAnd { .. } => out.push_str("    i32.and\n"),
            Instruction::BooleanOr { .. } => out.push_str("    i32.or\n"),
            Instruction::Call { function, .. } => out.push_str(&format!("    call $f{function}\n")),
            _ => out.push_str("    ;; helper lowering omitted from archive\n"),
        }
    }

    fn emit_data(out: &mut String, bytes: &[u8]) {
        if bytes.is_empty() {
            return;
        }
        out.push_str("  (data (i32.const 4096) \"");
        for byte in bytes {
            match byte {
                b'"' => out.push_str("\\\""),
                b'\\' => out.push_str("\\\\"),
                0x20..=0x7e => out.push(*byte as char),
                _ => out.push_str(&format!("\\{:02x}", byte)),
            }
        }
        out.push_str("\")\n");
    }
}

// Archive conclusion: the CFG representation was promising, but retrofitting
// dynamic value tags and precise lexical environments cost more than replacing
// the prototype. The release backend did not inherit these type or ABI choices.
