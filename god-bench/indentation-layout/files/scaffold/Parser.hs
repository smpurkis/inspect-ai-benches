module Parser (parseProgram) where

import Token

parseProgram :: [Token] -> Either String ()
parseProgram [] = Right ()
parseProgram toks = do
  rest <- block toks
  case rest of
    [] -> Right ()
    _ -> Left ("trailing tokens: " ++ show rest)

block :: [Token] -> Either String [Token]
block (TVOpen:xs) = declarations TVClose xs
block (TLBrace:xs) = declarations TRBrace xs
block xs = Left ("expected block, got " ++ show (take 1 xs))

declarations :: Token -> [Token] -> Either String [Token]
declarations close (x:xs) | x == close = Right xs
declarations close xs = do
  afterDecl <- declaration xs
  case afterDecl of
    (TVSemi:rest) -> declarations close rest
    (TSemi:rest) -> declarations close rest
    (x:rest) | x == close -> Right rest
    _ -> Left ("expected declaration separator, got " ++ show (take 1 afterDecl))

declaration :: [Token] -> Either String [Token]
declaration (TIdent _:TEquals:xs) = expression xs
declaration xs = Left ("expected declaration, got " ++ show (take 3 xs))

expression :: [Token] -> Either String [Token]
expression (TLet:xs) = do
  afterBlock <- block xs
  case afterBlock of
    (TIn:rest) -> expression rest
    _ -> Left "let block requires in"
expression (TLParen:xs) = do
  rest <- expression xs
  case rest of
    (TRParen:more) -> postfix more
    _ -> Left "missing )"
expression (TIdent _:xs) = postfix xs
expression xs = Left ("expected expression, got " ++ show (take 2 xs))

postfix :: [Token] -> Either String [Token]
postfix (TWhere:xs) = block xs
postfix xs = Right xs
