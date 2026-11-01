-- SQE ECM export (v0.41.210, XO 2026-10-30): tells the mission's results hook whether YOUR jammer is transmitting.
--
-- WHAT IT DOES: four times a second (v0.41.219) it reads your jet's ECM lamp (a cockpit argument) and writes  Saved Games\DCS\Logs\SQE_ecm.flag  as
--     <0 or 1> <model time>
-- The SQE results hook (the mission-side script) reads that file when a radar missile is fired at you. A missing file, a stale one (older than 5 s) or a
-- jet this script does not know means SQE's old rule: your jammer counts as on over the attack leg only. So without this script you lose nothing.
-- The file is written when the lamp CHANGES, plus a heartbeat once a second so the hook's 5 s freshness check stays satisfied (about one small write a second).
-- It changes nothing in DCS, it reads no keys, and it writes only that one file.
--
-- JETS: the F-16C is live (argument 102, "ECM Light (green)", confirmed in XO's 2026-10-28 log with a pod hung). The F/A-18C, F-14B and A-10C arguments below are
-- from DCS-BIOS and NOT flown: they stay OFF (enabled = false) until XO has flown them with and without a pod. FC3 jets (F-15C) have no readable lamp: use
-- the mission's F10 > Other > SQE ECM Switch toggle (and SQE ECM OFF) instead.
--
-- FC3 JETS, WHAT WAS TRIED (2026-11, XO's F-15C flights): nothing the Export side can read follows the jet's ECM or electrical power: LoGetSightingSystemInfo.ECM_on, the
-- LoGetMCPState flags, LoGetActivityLevel (missing), list_indication(0), GetDevice(0) (nil), list_cockpit_params (flight sensors only), the external model arguments and
-- LoGetTWSInfo (the RWR table: Mode stayed 0, Emitters are other radars). Hence the manual F10 commands above.
--
-- HOW TO INSTALL: SQE does it for you (Settings > DCS integration > Install ECM script). By hand: copy THIS file to Saved Games\DCS\Scripts\sqe_ecm_export.lua and add
-- at the END of Saved Games\DCS\Scripts\Export.lua (create it if it does not exist; this file chains the previous export functions instead of replacing them):
--   --[[SQE ECM EXPORT]]dofile(lfs.writedir() .. [[Scripts\sqe_ecm_export.lua]])
-- Remove the line (and the file) to uninstall.

local JETS = {
  ["F-16C_50"] = { arg = 102,  enabled = true },      -- LIGHT_ECM (green): 1 = transmitting
  ["FA-18C_hornet"] = { arg = 24,   enabled = false }, -- LH_ADV_XMIT advisory lamp (not flown)
  ["F-14B"] = { arg = 2203, enabled = false },         -- RIO_XMIT_LIGHT (not flown; RIO cockpit may not be readable from the pilot seat)
  ["A-10C_2"] = { arg = 361, enabled = false },        -- CMSP_JMR switch, 3 positions (not flown)
}

local SQE_ECM = { file = nil, name = nil, next_t = 0, last = nil, last_w = -10 }
local POLL_S, BEAT_S = 0.25, 1.0
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
  SQE_ECM.next_t = 0; SQE_ECM.last = nil; SQE_ECM.last_w = -10
  pcall(os.remove, path())                              -- a flag left from an earlier flight must never be read as this one's
end

function LuaExportStop()
  pcall(os.remove, path())
  if prev_stop then pcall(prev_stop) end
end

function LuaExportActivityNextEvent(t)
  local nxt = prev_next and prev_next(t) or (t + POLL_S)
  if t >= SQE_ECM.next_t then
    SQE_ECM.next_t = t + POLL_S
    local j = SQE_ECM.name and JETS[SQE_ECM.name]
    if j and j.enabled then
      local ok, v = pcall(function() return GetDevice(0):get_argument_value(j.arg) end)
      if ok and v ~= nil then
        local okm, mt = pcall(LoGetModelTime)
        local on = v > 0.5
        if on ~= SQE_ECM.last or t - SQE_ECM.last_w >= BEAT_S then
          write_flag(on, okm and mt or t)
          SQE_ECM.last, SQE_ECM.last_w = on, t
        end
      end
    end
  end
  return math.min(nxt or (t + POLL_S), t + POLL_S)
end
