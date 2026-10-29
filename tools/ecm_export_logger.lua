-- SQE cockpit change logger (XO 2026-10-28): discovery tool for the ECM switch probe. NOT verified in DCS yet.
--
-- WHAT IT DOES: while you fly, it writes every CHANGE of a cockpit value to  Saved Games\DCS\Logs\SQE_cockpit_changes.log  with the model time,
-- so pressing the ECM binding shows which value that button moves. It reads two things:
--   1. list_cockpit_params()  - the text list of every named cockpit parameter of the jet (the same values the Mission Editor's "Cockpit Parameter"
--      triggers read). Each line is logged as   PARAM <name> <old> -> <new>.
--   2. GetDevice(0):get_argument_value(i), i = 0..999  - the raw cockpit arguments (switch and light positions). Logged as   ARG <i> <old> -> <new>.
--   3. (v2, F-15C RWR flashing symbol) LoGetTWSInfo() (the RWR: mode and emitters), LoGetMCPState() (warning panel) and list_indication(0..20)
--      (display text). Logged as   TWS ..., MCP ..., IND <device> ... when they change. An argument-read check line says whether GetDevice(0) works.
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

local SQE = { file = nil, params = {}, args = {}, n_params = 0, t_next = 0, started = false, rawshown = false, step = 0.25, ind = {}, last_tws = nil, last_mcp = nil }

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
  SQE.ind, SQE.last_tws, SQE.last_mcp, SQE.argnote = {}, nil, nil, nil
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
    local name, val = string.match(line, "^%s*(.-)%s*:%s*([^:]-)%s*;?%s*$")      -- split at the LAST colon: "ExternalFM:HumanInfo:nz:0.0" is one name
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
  if not ok or not dev then
    if not SQE.argnote then sqe_log("NOTE GetDevice(0) is not available: no ARG lines will follow (" .. tostring(dev) .. ")"); SQE.argnote = true end
    return
  end
  if not SQE.argnote then
    local nn = 0
    for i = 0, 999 do local okv, v = pcall(dev.get_argument_value, dev, i); if okv and type(v) == "number" then nn = nn + 1 end end
    sqe_log("NOTE GetDevice(0): " .. nn .. " of 1000 cockpit arguments readable")
    SQE.argnote = true
  end
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

local function dump(t, d)
  if type(t) ~= "table" then return tostring(t) end
  if (d or 0) > 3 then return "{...}" end
  local keys = {}
  for k in pairs(t) do keys[#keys + 1] = tostring(k) end
  table.sort(keys)
  local out = {}
  for _, k in ipairs(keys) do
    local v = t[k]; if v == nil then v = t[tonumber(k)] end
    out[#out + 1] = k .. "=" .. dump(v, (d or 0) + 1)
  end
  return "{" .. table.concat(out, ",") .. "}"
end

local function sample_extra()
  -- RWR: log the mode and the emitter COUNT on change (emitter powers move all the time); the full dump when mode or count changes
  if type(LoGetTWSInfo) == "function" then
    local ok, tw = pcall(LoGetTWSInfo)
    local sig
    if ok and type(tw) == "table" then
      local n = 0; if type(tw.Emitters) == "table" then for _ in pairs(tw.Emitters) do n = n + 1 end end
      sig = "mode=" .. tostring(tw.Mode) .. " emitters=" .. n
      if sig ~= SQE.last_tws then sqe_log(sqe_now() .. " TWS " .. sig .. " | " .. dump(tw)) end
    else
      sig = "none:" .. tostring(tw)
      if sig ~= SQE.last_tws then sqe_log(sqe_now() .. " TWS " .. sig) end
    end
    SQE.last_tws = sig
  end
  if type(LoGetMCPState) == "function" then
    local ok, m = pcall(LoGetMCPState)
    local sig = ok and dump(m) or ("error " .. tostring(m))
    if sig ~= SQE.last_mcp then sqe_log(sqe_now() .. " MCP " .. sig); SQE.last_mcp = sig end
  end
  if type(list_indication) == "function" then
    for dev = 0, 20 do
      local ok, txt = pcall(list_indication, dev)
      local sig = (ok and type(txt) == "string") and txt or ""
      if sig ~= (SQE.ind[dev] or "") then
        sqe_log(sqe_now() .. " IND " .. dev .. " (" .. #sig .. " chars) " .. string.sub(string.gsub(sig, "[\r\n]+", " | "), 1, 600))
        SQE.ind[dev] = sig
      end
    end
  end
end

function LuaExportActivityNextEvent(t)
  local tNext = t + SQE.step
  if SQE.started and SQE.file then
    pcall(sample_params)
    pcall(sample_args)
    pcall(sample_extra)
  end
  if prev_next then
    local ok, tn = pcall(prev_next, t)
    if ok and tn and tn < tNext then tNext = tn end      -- keep the other tool's earlier schedule as well
  end
  return tNext
end
