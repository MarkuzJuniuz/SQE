-- SQE ECM export (v0.41.210, XO 2026-10-30): tells the mission's results hook whether YOUR jammer is transmitting.
--
-- WHAT IT DOES: four times a second (v0.41.219) it reads your jet's ECM lamp (a cockpit argument), or on the A-10C II the jammer window of its countermeasure display, and writes  Saved Games\DCS\Logs\SQE_ecm.flag  as
--     <0 or 1> <model time>
-- and the same line into the sibling  Saved Games\DCS_Server\Logs  when that folder exists: a mission on the dedicated server on this PC reads that one.
-- The SQE results hook (the mission-side script) reads that file when a radar missile is fired at you. A missing file, a stale one (older than 5 s) or a
-- jet this script does not know means SQE's old rule: your jammer counts as on over the attack leg only. So without this script you lose nothing.
-- The file is written when the lamp CHANGES, plus a heartbeat once a second so the hook's 5 s freshness check stays satisfied (about one small write a second).
-- It changes nothing in DCS, it reads no keys, and it writes only that flag.
--
-- JETS: the F-16C is live (argument 102, "ECM Light (green)", confirmed in XO's 2026-10-28 log with a pod hung). The A-10C II is live (v0.41.685, probe flown 2026-11-25): it has no jammer lamp, so the script reads
-- the CMSC display's jammer window (element txt_JMR: OFF, SBY or OPR; OPR blinks). The F/A-18C and F-14B arguments below are from DCS-BIOS and NOT flown: they stay OFF (enabled = false) until XO has flown
-- them with and without a pod. FC3 jets (F-15C) have no readable lamp: use
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
  ["A-10C_2"] = { window = "txt_JMR", enabled = true },  -- the CMSC jammer window: OFF, SBY or OPR
}

local SQE_ECM = { file = nil, name = nil, next_t = 0, last = nil, last_w = -10 }
local POLL_S, BEAT_S = 0.25, 1.0
local FIRST_INDICATION, LAST_INDICATION = 8, 30       -- the A-10C II's window was on display 8; the others are searched if it is not there
local SEARCH_AGAIN_S = 5.0                            -- the window is missing while the panel has no power: look through all displays only this often
local BLINK_HOLD_S = 1.5                              -- OPR blinks, about half a second shown and half blank
local prev_start, prev_stop, prev_next = LuaExportStart, LuaExportStop, LuaExportActivityNextEvent

-- "C:\Users\You\Saved Games\DCS\" -> "C:\Users\You\Saved Games\"
local function parent_folder(path)
  return (string.gsub(path, "[^\\/]+[\\/]*$", ""))
end

-- Single player reads the flag in your own folder; a mission on the dedicated server on this PC reads the one in the server's folder.
local function paths()
  local own = lfs.writedir()
  return { own .. [[Logs\SQE_ecm.flag]], parent_folder(own) .. [[DCS_Server\Logs\SQE_ecm.flag]] }
end

local function remove_flags()                           -- a flag left from an earlier flight must never be read as this one's
  for _, flag_path in ipairs(paths()) do
    pcall(os.remove, flag_path)
  end
end

local function write_flag(on, t)
  for _, flag_path in ipairs(paths()) do
    local ok, f = pcall(io.open, flag_path, "w")       -- no server folder: the open gives nothing and that copy is skipped
    if ok and f then f:write(string.format("%d %.2f\n", on and 1 or 0, t)); f:close() end
  end
end

-- the text of the jammer window on one display, or nil when that display does not carry it
local function window_on(number, element)
  local ok, text = pcall(list_indication, number)
  if not ok or type(text) ~= "string" then return nil end
  return string.match(text, element .. "\r?\n([^\r\n]*)")
end

local function window_text(element, t)
  local shown = window_on(SQE_ECM.indication or FIRST_INDICATION, element)
  if shown then return shown end
  if t < (SQE_ECM.search_t or 0) then return nil end
  SQE_ECM.search_t = t + SEARCH_AGAIN_S
  for number = 0, LAST_INDICATION do
    shown = window_on(number, element)
    if shown then
      SQE_ECM.indication = number
      return shown
    end
  end
  return nil
end

-- is the jammer transmitting? true / false, or nil when it cannot be read (then nothing is written and SQE keeps its old rule)
local function transmitting(jet, t)
  if jet.arg then
    local ok, v = pcall(function() return GetDevice(0):get_argument_value(jet.arg) end)
    if ok and v ~= nil then return v > 0.5 end
    return nil
  end
  local shown = window_text(jet.window, t)
  if not shown then return nil end
  if string.match(shown, "^%s*OPR") then
    SQE_ECM.opr_t = t
    return true
  end
  if string.match(shown, "^%s*SBY") or string.match(shown, "^%s*OFF") then
    SQE_ECM.opr_t = nil
    return false
  end
  -- neither word: the blank half of the blink
  return SQE_ECM.opr_t ~= nil and t - SQE_ECM.opr_t < BLINK_HOLD_S
end

function LuaExportStart()
  if prev_start then pcall(prev_start) end
  local ok, n = pcall(function() return LoGetSelfData().Name end)
  SQE_ECM.name = ok and n or nil
  SQE_ECM.next_t = 0; SQE_ECM.last = nil; SQE_ECM.last_w = -10
  SQE_ECM.indication = nil; SQE_ECM.search_t = 0; SQE_ECM.opr_t = nil
  remove_flags()
end

function LuaExportStop()
  remove_flags()
  if prev_stop then pcall(prev_stop) end
end

function LuaExportActivityNextEvent(t)
  local nxt = prev_next and prev_next(t) or (t + POLL_S)
  if t >= SQE_ECM.next_t then
    SQE_ECM.next_t = t + POLL_S
    local j = SQE_ECM.name and JETS[SQE_ECM.name]
    if j and j.enabled then
      local ok, on = pcall(transmitting, j, t)
      if ok and on ~= nil then
        local okm, mt = pcall(LoGetModelTime)
        if on ~= SQE_ECM.last or t - SQE_ECM.last_w >= BEAT_S then
          write_flag(on, okm and mt or t)
          SQE_ECM.last, SQE_ECM.last_w = on, t
        end
      end
    end
  end
  return math.min(nxt or (t + POLL_S), t + POLL_S)
end
