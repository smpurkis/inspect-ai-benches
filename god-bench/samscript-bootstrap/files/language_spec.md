# SamScript Language Specification v1.0

## Overview

SamScript is a dynamically-typed, expression-oriented scripting language. Programs consist of top-level function declarations. Execution begins at the `main()` function.

## Lexical Structure

### Comments
Single-line comments start with `//` and extend to the end of the line.

### Identifiers
Identifiers start with a letter or underscore, followed by letters, digits, or underscores.

### Keywords
```
fn  let  const  if  else  loop  break  continue  return
from  import  and  or  not  true  false  none
```

### Literals

**Numbers**: All numbers are 64-bit floating point. Examples: `42`, `3.14`, `0.5`

**Strings**: Enclosed in double quotes. Support escape sequences `\n`, `\t`, `\\`, `\"`, `\$`.

**String interpolation**: Use `${}` inside strings to embed expressions:
```
"hello ${name}"
"${a + b} is the sum"
```

**Booleans**: `true` and `false`

**None**: The `none` literal represents the absence of a value.

## Types

SamScript has 6 value types:

| Type     | Description                    | Example              |
|----------|--------------------------------|----------------------|
| `number` | 64-bit float (f64)             | `42`, `3.14`         |
| `string` | UTF-8 string                   | `"hello"`            |
| `bool`   | Boolean                        | `true`, `false`      |
| `none`   | Null/absent value              | `none`               |
| `list`   | Ordered, mutable sequence      | `[1, 2, 3]`         |
| `dict`   | String-keyed mutable map       | `{"a": 1, "b": 2}`  |

## Operators

### Arithmetic
| Operator | Description       | Example    |
|----------|-------------------|------------|
| `+`      | Addition          | `a + b`    |
| `-`      | Subtraction       | `a - b`    |
| `*`      | Multiplication    | `a * b`    |
| `/`      | Division          | `a / b`    |
| `%`      | Modulo            | `a % b`    |
| `**`     | Exponentiation    | `a ** b`   |
| `-`      | Unary negation    | `-a`       |

### Comparison
| Operator | Description        |
|----------|--------------------|
| `==`     | Equal              |
| `!=`     | Not equal          |
| `<`      | Less than          |
| `>`      | Greater than       |
| `<=`     | Less or equal      |
| `>=`     | Greater or equal   |

### Logical
| Operator | Description        |
|----------|--------------------|
| `and`    | Logical AND        |
| `or`     | Logical OR         |
| `not`    | Logical NOT        |

### String Concatenation
The `..` operator concatenates two values as strings:
```
"hello" .. " " .. "world"   // "hello world"
42 .. " items"               // "42 items"
```

### Operator Precedence (lowest to highest)
1. `or`
2. `and`
3. `==`, `!=`
4. `<`, `>`, `<=`, `>=`
5. `+`, `-`, `..`
6. `*`, `/`, `%`
7. `**` (right-associative)
8. Unary `-`, `not`
9. Call `()`, Index `[]`, Field `.`

### Compound Assignment
`+=`, `-=`, `*=`, `/=`, `%=` — shorthand for `x = x op expr`.

## Declarations

### Variables
```
let x = 10          // mutable variable
const PI = 3.14159  // immutable constant — reassignment is a runtime error
```

Variables declared with `let` can be reassigned. Variables declared with `const` cannot.

All variables must be declared before use. Using an undeclared variable is a runtime error.

### Functions
```
fn name(param1, param2) {
    // body
}
```

**Optional type hints** (documentation only, not enforced at runtime):
```
fn add(a: number, b: number) -> number {
    return a + b
}
```

**Default parameter values**:
```
fn greet(name, times = 1) {
    // ...
}
```

Parameters with defaults must come after parameters without defaults.

**Return values**: Use `return expr` to return a value. Functions that don't explicitly return produce `none`.

## Statements

### Expression Statement
Any expression can be used as a statement:
```
print("hello")
add(1, 2)
```

### Variable Declaration
```
let x = 42
const y = "immutable"
```

### Assignment
```
x = 10
x += 5
list[0] = "new"
dict["key"] = value
```

Assignment to an undeclared variable is an error. Use `let` to declare first.

### If / Else If / Else
```
if condition {
    // ...
} else if other_condition {
    // ...
} else {
    // ...
}
```

Braces are always required. There are no parentheses around conditions.

### Loop
```
loop {
    if done { break }
    // ...
    continue
}
```

SamScript has only `loop` — no `for` or `while`. Use `loop` with `break` for all iteration.

### Break and Continue
`break` exits the innermost loop. `continue` skips to the next iteration.

### Return
```
return          // returns none
return expr     // returns the value of expr
```

## Built-in Functions

| Function           | Description                                            |
|--------------------|--------------------------------------------------------|
| `print(value)`     | Print value to stdout followed by newline              |
| `input()`          | Read a line from stdin, return as string               |
| `len(value)`       | Return length of string, list, or dict                 |
| `type(value)`      | Return type name as string: "number", "string", etc.   |
| `str(value)`       | Convert value to string                                |
| `num(value)`       | Convert string to number, error if invalid             |
| `assert(cond)`     | Crash with error if condition is false                 |
| `assert(cond, msg)`| Crash with custom error message if condition is false  |
| `read_file(path)`  | Read file at path, return contents as string           |
| `args()`           | Return CLI arguments passed after `--` as a list       |

## Modules and Imports

```
from math import sqrt, abs
from utils import helper
```

- Module names map to files: `from math import x` looks for `math.sam` in the same directory.
- Only the listed names are brought into scope.
- Circular imports are a runtime error (not a hang).
- Transitive imports work: if A imports from B and B imports from C, C is loaded first.

## Number Formatting

When printed, numbers that are exact integers display without a decimal point:
- `10.0` prints as `10`
- `3.14` prints as `3.14`
- `1000.0` prints as `1000`

## Scoping Rules

- Variables are block-scoped. A variable declared inside `{ ... }` is not visible outside.
- Functions create a new scope. Parameters are local to the function.
- Inner scopes can read (but not assign to) variables from outer scopes unless shadowed by a `let`/`const` in the inner scope.
- Function declarations are hoisted to the top of the program — functions can call each other regardless of declaration order.

## Error Handling

SamScript has no try/catch. All errors crash the program with a stack trace.

Error messages should include:
- The error type and description
- The file and line number where the error occurred
- A stack trace showing the call chain

Example error output:
```
runtime error at line 5: division by zero
stack trace:
  at divide (line 5)
  at main (line 12)
```

## Program Entry Point

Every SamScript program must define a `main()` function. This is the entry point. If `main` is not defined, the toolchain must emit a clear error:
```
error: no 'main' function defined
```
