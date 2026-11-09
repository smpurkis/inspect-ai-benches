module Layout (LayoutError(..), insertLayout) where

import Token

data LayoutError
  = BadDedent Int Int
  | UnexpectedClose Int Int
  | UnclosedExplicit
  | MissingBlock
  deriving (Eq, Show)

-- This starter loses enclosing indentation levels and treats explicit braces as
-- ordinary tokens. It passes the simplest single-declaration case only.
insertLayout :: [Located Token] -> Either LayoutError [Token]
insertLayout [] = Right []
insertLayout toks = Right (TVOpen : go (column (head toks)) 0 toks ++ [TVClose])
  where
    go _ _ [] = []
    go indent previousLine (Located line col tok : rest)
      | previousLine /= 0 && line /= previousLine && col == indent =
          TVSemi : tok : go indent line rest
      | otherwise = tok : go indent line rest
