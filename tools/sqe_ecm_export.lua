-- SQE ECM export (v0.41.210, XO 2026-10-30): tells the mission's results hook whether YOUR jammer is transmitting.
--
-- WHAT IT DOES: once a second it reads your jet's ECM lamp (a cockpit argument) and writes  Saved Games\DCS\Logs\SQE_ecm.flag  as
--     <0 or 1> <model time>
-- The SQE results hook (the mission-side script) reads that file when a radar missile is fired at you. A missing file, a stale one (older than 5 s) or a
-- jet this script does not know means SQE's old rule: your jammer counts as on over the attack leg only. So without this script you lose nothing.
-- It changes nothing in DCS, it reads no keys, and it writes only that one file.
--
-- JETS: the F-16C is live (argument 102, "ECM Light (green)", confirmed in XO's 2026-10-28 log with a pod hung). The F/A-18C, F-14B and A-10C arguments below are
-- from DCS-BIOS and NOT flown: they stay OFF (enabled = false) until XO has flown them with and without a pod. FC3 jets (F-15C) have no readable lamp: use
-- the mission's F10 > Other > ECM ON / ECM OFF commands instead.
--
-- HOW TO INSTALL (one line in YOUR Export.lua, like the cockpit logger; this file chains the previous export functions instead of replacing them):
--   open  Saved Games\DCS\Scripts\Export.lua  (create it if it does not exist) and add at the END:
--       dofile(lfs.writedir() .. [[Scripts\sqe_ecm_export.lua]])
--   and copy THIS file to  Saved Games\DCS\Scripts\sqe_ecm_export.lua . Remove the line to uninstall.

local JETS = {
  ["F-16C_50"] = { arg = 102,  enabled = true },      -- LIGHT_ECM (green): 1 = transmitting
  ["FA-18C_hornet"] = { arg = 24,   enabled = false }, -- LH_ADV_XMIT advisory lamp (not flown)
  ["F-14B"] = { arg = 2203, enabled = false },         -- RIO_XMIT_LIGHT (not flown; RIO cockpit may not be readable from the pilot seat)
  ["A-10C_2"] = { arg = 361, enabled = false },        -- CMSP_JMR switch, 3 positions (not flown)
}

local SQE_ECM = { file = nil, name = nil, next_t = 0 }
local prev_start, prev_stop, prev_next = LuaExportStart, LuaExportStop, LuaExportActivityNextEvent

local function path() return lfs.writedir() .. [[Logs\SQE_ecm.flag]] end

local function write_flag(on, t)
  local ok, f = pcall(io.open, path(), "w")
  if ok and f then f:write(string.format("%d %.2f\n", on and 1 or 0, t)); f:close() end
end

function LuaExportStart()
  if prev_start then pcall(prev_start) end
  local ok, n = pcall(function() return LoGetSelfData().Name end)
  SQE_ECM.name = ok and n or nil
  SQE_ECM.next_t = 0
  pcall(os.remove, path())                              -- a flag left from an earlier flight must never be read as this one's
end

function LuaExportStop()
  pcall(os.remove, path())
  if prev_stop then pcall(prev_stop) end
end

function LuaExportActivityNextEvent(t)
  local nxt = prev_next and prev_next(t) or (t + 1)
  if t >= SQE_ECM.next_t then
    SQE_ECM.next_t = t + 1
    local j = SQE_ECM.name and JETS[SQE_ECM.name]
    if j and j.enabled then
      local ok, v = pcall(function() return GetDevice(0):get_argument_value(j.arg) end)
      if ok and v ~= nil then
        local okm, mt = pcall(LoGetModelTime)
        write_flag(v > 0.5, okm and mt or t)
      end
    end
  end
  return math.min(nxt or (t + 1), t + 1)
end
