/-
fvsmith DAG probe — comma-joined package modules are argv[0]; JSONL to argv[1]; goal user-names are argv[2:].

Walks the compiled environment at OLeanLevel.private with loadExts := true and emits
one JSON line per package-local constant:

  {record:"decl", name, user, module, kind, internal, typeDeps, valueDeps,
   file?, startLine?, endLine?, all?}

and, for every requested goal, one extra line carrying the grading truth:

  {record:"goal", name, statement, levelParams, noncomputable, isProp, isTypeFormer,
   executable, typeHash}

`statement` is the pretty-printed elaborated TYPE with `pp.fullNames`/`pp.universes` on, so it
re-elaborates against the sealed spec alone; the cutter freezes it into a sealed spec module and
the grader compares the agent's declaration to it up to `Meta.isDefEq`. Pretty-printing is done
for goals ONLY — doing it for every constant costs minutes and megabytes.

`executable` is noncomputable + type-shape derived (V7): a proof, a type former, or a
noncomputable def is never executable. `kind == "def"` alone is NOT a sufficient test.

Value is taken by matching ConstantInfo constructors directly (no ConstantInfo.value?).
Spans come from declarationRanges when the extension recorded them.

    lake env lean --run dag_probe.lean <Mod1,Mod2,...> [OUT.jsonl] [goal ...]
-/
import Lean
import Lean.DeclarationRange
open Lean

def kindOf : ConstantInfo → String
  | .axiomInfo _  => "axiom"
  | .defnInfo _   => "def"
  | .thmInfo _    => "theorem"
  | .opaqueInfo _ => "opaque"
  | .quotInfo _   => "quot"
  | .inductInfo _ => "inductive"
  | .ctorInfo _   => "ctor"
  | .recInfo _    => "rec"

/-- Direct constructor match — Lean 4.31 changed theorem `value?` behavior. -/
def valueOf : ConstantInfo → Option Expr
  | .thmInfo v    => some v.value
  | .defnInfo v   => some v.value
  | .opaqueInfo v => some v.value
  | _             => none

def allOf (n : Name) : ConstantInfo → List Name
  | .thmInfo v    => v.all
  | .defnInfo v   => v.all
  | .inductInfo v => v.all
  | .opaqueInfo v => v.all
  | _             => [n]

def jsonStrs (xs : Array Name) : Json :=
  Json.arr (xs.map (Json.str ·.toString))

def jsonNameList (xs : List Name) : Json :=
  Json.arr (xs.toArray.map (Json.str ·.toString))

/-- Grading truth for one goal: re-elaboratable statement text + the executable flag. -/
def goalJson (n : Name) (ci : ConstantInfo) : MetaM Json := do
  let stmt ← withOptions (fun o =>
      o.setBool `pp.all true |>.setBool `pp.fullNames true |>.setBool `pp.universes true) <|
    Lean.PrettyPrinter.ppExpr ci.type
  let sort ← Meta.inferType ci.type
  let isProp := sort == mkSort Level.zero
  let isTypeFormer ← Meta.forallTelescopeReducing ci.type fun _ b => pure b.isSort
  let noncomp := isNoncomputable (← getEnv) n
  let isDef := match ci with | .defnInfo _ => true | _ => false
  pure <| Json.mkObj [
    ("record", Json.str "goal"),
    ("name", Json.str n.toString),
    ("statement", Json.str (toString stmt)),
    ("levelParams", jsonNameList ci.levelParams),
    ("noncomputable", Json.bool noncomp),
    ("isProp", Json.bool isProp),
    ("isTypeFormer", Json.bool isTypeFormer),
    ("executable", Json.bool (isDef && !noncomp && !isProp && !isTypeFormer)),
    ("typeHash", Json.str (toString (hash ci.type)))]

unsafe def main (args : List String) : IO Unit := do
  let modsStr ← match args with
    | r :: _ => pure r
    | [] => throw <| IO.userError "dag_probe: missing package modules (argv[0])"
  let outPath : System.FilePath := args.drop 1 |>.headD "dag.jsonl"
  -- `String.toName` maps a malformed atom to `Name.anonymous`. Looking that up used to crash
  -- the probe on a phantom `[anonymous]` and hide the offending argv. Drop anonymous names
  -- here; Python already refuses them, and this is defense in depth for a stale caller.
  -- Never throw on the first missing goal — the Python post-check reports ALL of them
  -- together after a clean exit 0.
  let rawGoalArgs : List String := args.drop 2
  let goalNames : List Name := rawGoalArgs.map String.toName |>.filter (· != Name.anonymous)
  let pkgMods : List Name := (modsStr.splitOn ",").filter (· ≠ "") |>.map String.toName
    |>.filter (· != Name.anonymous)
  if pkgMods.isEmpty then
    throw <| IO.userError "dag_probe: empty package module list (argv[0])"
  if rawGoalArgs.any (fun s => s.toName == Name.anonymous) then
    IO.eprintln "dag_probe: skipped malformed goal argv that String.toName mapped to [anonymous]"
  let pkg : NameSet := pkgMods.foldl (fun s n => s.insert n) {}
  initSearchPath (← findSysroot)
  enableInitializersExecution
  let env ← importModules (pkgMods.toArray.map fun m => { module := m }) {} (loadExts := true) (level := .private)
  let srcPath ← getSrcSearchPath
  let h ← IO.FS.Handle.mk outPath IO.FS.Mode.write
  let mods := env.header.moduleNames
  let data := env.header.moduleData
  let mut count := 0
  let mut goals : Array (Name × ConstantInfo) := #[]
  for i in [0:mods.size] do
    let m := mods[i]!
    if pkg.contains m then
      let file? ← do
        match (← srcPath.findModuleWithExt "lean" m) with
        | some p => pure (some p.toString)
        | none => pure none
      for n in data[i]!.constNames do
        if env.getModuleIdxFor? n == some i then if let some ci := env.find? n then
          let user := (privateToUserName? n).getD n
          if goalNames.contains user then
            goals := goals.push (user, ci)
          let tdeps := ci.type.getUsedConstants
          let vdeps := match valueOf ci with
            | some v => v.getUsedConstants
            | none => #[]
          let allNames := allOf n ci
          let ranges? : Option DeclarationRanges :=
            declRangeExt.find? (level := .exported) env n <|>
              declRangeExt.find? (level := .server) env n
          let mut fields : Array (String × Json) := #[
            ("record", Json.str "decl"),
            ("name", Json.str n.toString),
            ("user", Json.str user.toString),
            ("module", Json.str m.toString),
            ("kind", Json.str (kindOf ci)),
            ("internal", Json.bool n.isInternal),
            ("typeDeps", jsonStrs tdeps),
            ("valueDeps", jsonStrs vdeps)]
          if let some fp := file? then
            fields := fields.push ("file", Json.str fp)
          if let some r := ranges? then
            fields := fields.push ("startLine", toJson r.range.pos.line)
            fields := fields.push ("endLine", toJson r.range.endPos.line)
          if allNames.length > 1 then
            fields := fields.push ("all", jsonNameList allNames)
          h.putStrLn (Json.mkObj fields.toList).compress
          count := count + 1
  -- Goal grading truth needs MetaM (pp + inferType); one pass, goals only.
  let act : MetaM (Array Json) := goals.mapM fun (u, ci) => goalJson u ci
  -- Large generated environments such as LeanGPU can have expression/dependency trees deeper
  -- than CoreM's default 1000, and real goal statements can exceed the 200k-heartbeat whnf
  -- default. This is a structural probe: neither depth nor heartbeats may reject a valid repo.
  let probeOptions := maxHeartbeats.set (maxRecDepth.set ({} : Options) 100000) 0
  let (rows, _) ← (Meta.MetaM.run' act).toIO
    { fileName := "<dag_probe>", fileMap := default, options := probeOptions,
      maxRecDepth := 100000, maxHeartbeats := 0 } { env }
  for r in rows do
    h.putStrLn r.compress
  IO.eprintln s!"dag_probe: wrote {count} constants, {rows.size} goals to {outPath}"
