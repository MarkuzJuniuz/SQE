-- SQE cockpit change logger (XO 2026-10-28): discovery tool for the ECM switch probe. NOT verified in DCS yet.
--
-- WHAT IT DOES: while you fly, it writes every CHANGE of a cockpit value to  Saved Games\DCS\Logs\SQE_cockpit_changes.log  with the model time,
-- so pressing the ECM binding shows which value that button moves. It reads two things:
--   1. list_cockpit_params()  - the text list of every named cockpit parameter of the jet (the same values the Mission Editor's "Cockpit Parameter"
--      triggers read). Each line is logged as   PARAM <name> <old> -> <new>.
--   2. GetDevice(0):get_argument_value(i), i = 0..999  - the raw cockpit arguments (switch and light positions). Logged as   ARG <i> <old> -> <new>.
-- It changes nothing in DCS. It only writes the log file. It does not read your keyboard: you press the button, the log shows what moved.
--
-- HOW TO INSTALL (one line, in YOUR file; nothing here writes into your folders):
--   open  Saved Games\DCS\Scripts\Export.lua  (create it if it does not exist) and add this line at the END:
--       dofile(lfs.writedir() .. [[Scripts\SQE_ecm_export_logger.lua]])
--   then copy THIS file to  Saved Games\DCS\Scripts\SQE_ecm_export_logger.lua   (rename it as shown).
--   To remove it, delete that line. If another tool (DCS-BIOS, SRS, TacView) already uses Export.lua, keep their lines: this file chains the
--   previous export functions instead of replacing them.
--
-- HOW TO USE: start the ECM probe mission for a jet (tools/ecm_probe.py), do the protocol in its briefing, then send SQE_cockpit_changes.log.
-- The first lines of the log say whether list_cockpit_params() worked, how many parameters it returned and show its first 20 lines, so we learn the
-- format even if parsing fails.

local SQE = { file = nil, params = {}, args = {}, n_params = 0, t_next = 0, started = false, rawshown = false, step = 0.25 }

local function sqe_log(s)
  if SQE.file then SQE.file:write(s .. "\n"); SQE.file:flush() end
end

local function sqe_now()
  local ok, t = pcall(LoGetModelTime)
  if ok and t then return string.format("%.2f", t) end
  return string.format("%.2f", os.clock())
end

local prev_start = LuaExportStart
local prev_stop = LuaExportStop
local prev_next = LuaExportActivityNextEvent

function LuaExportStart()
  if prev_start then pcall(prev_start) end
  local ok, f = pcall(io.open, lfs.writedir() .. [[Logs\SQE_cockpit_changes.log]], "w")
  if ok and f then SQE.file = f end
  SQE.params, SQE.args, SQE.n_params, SQE.rawshown, SQE.started = {}, {}, 0, false, true
  local okn, name = pcall(function() return LoGetSelfData().Name end)
  sqe_log("SQE cockpit change logger started. Aircraft: " .. tostring(okn and name or "unknown"))
end

function LuaExportStop()
  sqe_log("SQE cockpit change logger stopped.")
  if SQE.file then pcall(function() SQE.file:close() end); SQE.file = nil end
  if prev_stop then pcall(prev_stop) end
end

local function sample_params()
  if type(list_cockpit_params) ~= "function" then
    if not SQE.rawshown then sqe_log("NOTE list_cockpit_params is not available in this Export environment (only ARG lines will follow)"); SQE.rawshown = true end
    return
  end
  local ok, txt = pcall(list_cockpit_params)
  if not ok or type(txt) ~= "string" then
    if not SQE.rawshown then sqe_log("NOTE list_cockpit_params() failed: " .. tostring(txt)); SQE.rawshown = true end
    return
  end
  local count, shown = 0, {}
  for line in string.gmatch(txt, "[^\r\n]+") do
    local name, val = string.match(line, "^%s*([%w_%.%-%[%]]+)%s*[:=]%s*(.-)%s*;?%s*$")
    if name then
      count = count + 1
      local old = SQE.params[name]
      if old ~= nil and old ~= val then sqe_log(sqe_now() .. " PARAM " .. name .. " " .. tostring(old) .. " -> " .. tostring(val)) end
      SQE.params[name] = val
    end
    if #shown < 20 then shown[#shown + 1] = line end
  end
  if not SQE.rawshown then
    sqe_log("NOTE list_cockpit_params() returned " .. #txt .. " characters, " .. count .. " parsed parameters. First lines:")
    for _, l in ipairs(shown) do sqe_log("RAW " .. l) end
    SQE.rawshown = true
  end
end

local function sample_args()
  local ok, dev = pcall(GetDevice, 0)
  if not ok or not dev then return end
  for i = 0, 999 do
    local okv, v = pcall(dev.get_argument_value, dev, i)
    if okv and type(v) == "number" then
      v = math.floor(v * 1000 + 0.5) / 1000
      local old = SQE.args[i]
      if old ~= nil and old ~= v then sqe_log(sqe_now() .. " ARG " .. i .. " " .. tostring(old) .. " -> " .. tostring(v)) end
      SQE.args[i] = v
    end
  end
end

function LuaExportActivityNextEvent(t)
  local tNext = t + SQE.step
  if SQE.started and SQE.file then
    pcall(sample_params)
    pcall(sample_args)
  end
  if prev_next then
    local ok, tn = pcall(prev_next, t)
    if ok and tn and tn < tNext then tNext = tn end      -- keep the other tool's earlier schedule as well
  end
  return tNext
end
