module Token
  ( Token(..)
  , Located(..)
  , tokenize
  , renderToken
  ) where

import Data.Char (isAlpha, isAlphaNum)

data Token
  = TIdent String | TLet | TWhere | TIn | TEquals
  | TLParen | TRParen | TLBrace | TRBrace | TSemi
  | TVOpen | TVClose | TVSemi
  deriving (Eq, Show)

data Located a = Located
  { line :: !Int
  , column :: !Int
  , value :: a
  } deriving (Eq, Show)

tokenize :: String -> Either String [Located Token]
tokenize input
  | '\t' `elem` input = Left "tabs are not permitted"
  | otherwise = concat <$> traverse scanLine (zip [1..] (lines input))
  where
    scanLine (ln, text) = scan ln 1 text
    scan _ _ [] = Right []
    scan _ _ ('-':'-':_) = Right []
    scan ln col (c:cs)
      | c == ' ' = scan ln (col + 1) cs
      | isAlpha c || c == '_' =
          let (tailName, rest) = span (\x -> isAlphaNum x || x == '_') cs
              name = c : tailName
              tok = case name of
                "let" -> TLet
                "where" -> TWhere
                "in" -> TIn
                _ -> TIdent name
          in (Located ln col tok :) <$> scan ln (col + length name) rest
      | otherwise = case c of
          '=' -> one TEquals
          '(' -> one TLParen
          ')' -> one TRParen
          '{' -> one TLBrace
          '}' -> one TRBrace
          ';' -> one TSemi
          _ -> Left ("unknown character at " ++ show ln ++ ":" ++ show col)
      where
        one tok = (Located ln col tok :) <$> scan ln (col + 1) cs

renderToken :: Token -> String
renderToken tok = case tok of
  TIdent name -> "id:" ++ name
  TLet -> "let"
  TWhere -> "where"
  TIn -> "in"
  TEquals -> "="
  TLParen -> "("
  TRParen -> ")"
  TLBrace -> "{"
  TRBrace -> "}"
  TSemi -> ";"
  TVOpen -> "<open>"
  TVClose -> "<close>"
  TVSemi -> "<semi>"
