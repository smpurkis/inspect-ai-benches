module Main where

import Layout (insertLayout)
import Parser (parseProgram)
import System.Environment (getArgs)
import System.Exit (die)
import Token (renderToken, tokenize)

main :: IO ()
main = do
  args <- getArgs
  case args of
    [mode, path] -> do
      source <- readFile path
      positioned <- either die pure (tokenize source)
      laidOut <- either (die . show) pure (insertLayout positioned)
      case mode of
        "layout" -> mapM_ (putStrLn . renderToken) laidOut
        "parse" -> either die (const (putStrLn "ok")) (parseProgram laidOut)
        _ -> die "mode must be layout or parse"
    _ -> die "usage: layout-harness MODE FILE"
