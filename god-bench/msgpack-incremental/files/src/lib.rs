mod decode;

pub use decode::Decoder;

pub const MAX_CONTAINER_ITEMS: usize = 100_000;

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Value {
    Nil,
    Bool(bool),
    Integer(i64),
    Array(Vec<Value>),
    Map(Vec<(Value, Value)>),
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum DecodeError {
    Malformed,
    NonCanonicalInteger,
    IntegerOutOfRange,
    DepthLimit,
    ContainerTooLarge,
    Incomplete,
    Poisoned,
}

impl std::fmt::Display for DecodeError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{self:?}")
    }
}

impl std::error::Error for DecodeError {}
