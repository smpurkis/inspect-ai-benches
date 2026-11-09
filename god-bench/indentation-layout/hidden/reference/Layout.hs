module Layout (LayoutError(..), insertLayout) where

import Token

data LayoutError
  = BadDedent Int Int
  | UnexpectedClose Int Int
  | UnclosedExplicit
  | MissingBlock
  deriving (Eq, Show)

data Kind = Root | LetBlock | WhereBlock | Explicit deriving (Eq)
data Context = Context Kind Int

insertLayout :: [Located Token] -> Either LayoutError [Token]
insertLayout [] = Right []
insertLayout toks@(Located _ firstColumn _ : _) = do
  (_, _, _, reversed) <- walk [Context Root firstColumn] Nothing 0 Nothing [TVOpen] toks
  pure (reverse reversed)
  where
    walk contexts pending previousLine _ output [] =
      case pending of
        Just _ -> Left MissingBlock
        Nothing
          | any isExplicit contexts -> Left UnclosedExplicit
          | otherwise -> Right ([], Nothing, previousLine, closeAll contexts output)
    walk contexts pending previousLine previousToken output (Located currentLine currentColumn token : rest) = do
      let (openedContexts, openedOutput, justOpened) = case pending of
            Just kind | token /= TLBrace ->
              (Context kind currentColumn : contexts, TVOpen : output, True)
            _ -> (contexts, output, False)
      (indentedContexts, indentedOutput) <-
        if previousLine /= 0 && currentLine /= previousLine && not justOpened && token /= TIn
          then adjust False currentLine currentColumn token previousToken openedContexts openedOutput
          else Right (openedContexts, openedOutput)
      (tokenContexts, beforeToken) <- case token of
        TIn -> closeLet indentedContexts indentedOutput
        TRBrace -> closeExplicit currentLine currentColumn indentedContexts indentedOutput
        _ -> Right (indentedContexts, indentedOutput)
      let finalContexts = if token == TLBrace
            then Context Explicit 0 : tokenContexts
            else tokenContexts
          nextPending = case token of
            TLet -> Just LetBlock
            TWhere -> Just WhereBlock
            _ -> Nothing
      walk finalContexts nextPending currentLine (Just token) (token : beforeToken) rest

    isExplicit (Context kind _) = kind == Explicit

    closeAll [] output = output
    closeAll (_ : contexts) output = closeAll contexts (TVClose : output)

    adjust popped lineNumber col token previous contexts output =
      case contexts of
        [] -> Left (BadDedent lineNumber col)
        Context Explicit _ : _ -> Right (contexts, output)
        Context _ indent : more
          | col < indent -> adjust True lineNumber col token previous more (TVClose : output)
          | col > indent && popped -> Left (BadDedent lineNumber col)
          | col > indent -> Right (contexts, output)
          | suppress token previous -> Right (contexts, output)
          | otherwise -> Right (contexts, TVSemi : output)

    suppress token previous =
      token `elem` [TIn, TRBrace, TSemi] || previous `elem` [Just TLBrace, Just TSemi]

    closeLet contexts output
      | hasLet contexts = seek contexts output
      | otherwise = Right (contexts, output)
      where
        hasLet [] = False
        hasLet (Context Explicit _ : _) = False
        hasLet (Context LetBlock _ : _) = True
        hasLet (_ : more) = hasLet more
        seek [] out = Right ([], out)
        seek allContexts@(Context Explicit _ : _) out = Right (allContexts, out)
        seek (Context LetBlock _ : more) out = Right (more, TVClose : out)
        seek (_ : more) out = seek more (TVClose : out)

    closeExplicit lineNumber col contexts output = case contexts of
      [] -> Left (UnexpectedClose lineNumber col)
      Context Explicit _ : more -> Right (more, output)
      _ : more -> closeExplicit lineNumber col more (TVClose : output)
