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
-- PROBE (v0.41.226, XO 2026-11-01): for a jet that has no enabled lamp above (the FC3 jets), once a second it also writes the jet's own export tables to dcs.log
-- as "SQE EXPORT probe: ..." whenever they change: LoGetSightingSystemInfo (documented to hold ECM_on / radar_on), LoGetMCPState, and LoGetEngineInfo
-- (numbers rounded to whole units); v0.41.229 also dumps list_cockpit_params() once and logs each entry that changes ("SQE EXPORT param NAME a -> b"). It is read-only; it is how XO and Crew Chief look for a power / ECM signal on the F-15C. At most 1500 lines per flight.
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

local SQE_ECM = { file = nil, name = nil, next_t = 0, last = nil, last_w = -10, probe_t = 0, probe_last = nil, probe_n = 0 }
local POLL_S, BEAT_S = 0.25, 1.0
local prev_start, prev_stop, prev_next = LuaExportStart, LuaExportStop, LuaExportActivityNextEvent

local function path() return lfs.writedir() .. [[Logs\SQE_ecm.flag]] end

local function write_flag(on, t)
  local ok, f = pcall(io.open, path(), "w")
  if ok and f then f:write(string.format("%d %.2f\n", on and 1 or 0, t)); f:close() end
end

local function flat(v, prefix, out, depth)
  if type(v) == "table" then
    if depth < 3 then
      local keys = {}
      for k in pairs(v) do keys[#keys + 1] = tostring(k) end
      table.sort(keys)
      for _, ks in ipairs(keys) do
        local x = v[ks]
        if x == nil then x = v[tonumber(ks)] end
        flat(x, prefix .. "." .. ks, out, depth + 1)
      end
    end
  elseif type(v) == "number" then out[#out + 1] = prefix .. "=" .. string.format("%.0f", v)
  elseif type(v) == "boolean" or type(v) == "string" then out[#out + 1] = prefix .. "=" .. tostring(v) end
end

local function probe(t)                                  -- v0.41.226: look for a power / ECM signal in the export tables of a jet with no lamp
  if t < SQE_ECM.probe_t or SQE_ECM.probe_n >= 1500 then return end
  SQE_ECM.probe_t = t + 1.0
  local out = {}
  for _, f in ipairs({ "LoGetSightingSystemInfo", "LoGetMCPState", "LoGetEngineInfo" }) do
    local fn = _G[f]
    if fn then
      local ok, v = pcall(fn)
      if ok then flat(v, f, out, 0) else out[#out + 1] = f .. "=error" end
    else
      out[#out + 1] = f .. "=missing"
    end
  end
  -- v0.41.229 (XO 2026-11-01): LoGetActivityLevel (missing), list_indication(0) (no ECM text) and GetDevice(0) (nil) are ruled out for the F-15C. list_cockpit_params()
  -- exists (about 7.7 KB of "name:value" text): dump every name once, then log each entry whose value changes, so XO's ECM / power presses show up by name and time.
  local fp = _G["list_cockpit_params"]
  if fp then
    local ok, v = pcall(fp)
    if ok and type(v) == "string" then
      local cur = {}
      for k, val in v:gmatch("([^:\n;]+):([^;\n]*)") do cur[k] = val end
      local P = SQE_ECM.params
      if not P then
        P = {}; SQE_ECM.params = P; SQE_ECM.pn = 0; SQE_ECM.pcount = {}
        local pos = 1
        while pos <= #v do                               -- the whole list once, in 2000-character pieces
          pcall(log.write, "SQE", log.INFO, "SQE EXPORT params dump: " .. (v:sub(pos, pos + 1999):gsub("%s+", " ")))
          pos = pos + 2000
        end
      else
        for k, val in pairs(cur) do
          local o = P[k]
          if o ~= nil and o ~= val and SQE_ECM.pn < 800 and (SQE_ECM.pcount[k] or 0) < 40 then
            local a1, b1 = tonumber(o), tonumber(val)
            if not (a1 and b1) or math.abs(a1 - b1) >= 0.05 then
              SQE_ECM.pn = SQE_ECM.pn + 1
              SQE_ECM.pcount[k] = (SQE_ECM.pcount[k] or 0) + 1
              pcall(log.write, "SQE", log.INFO, string.format("SQE EXPORT param %s %s -> %s t=%.0f", k, o, val, t))
            end
          end
        end
      end
      for k, val in pairs(cur) do P[k] = val end
    else
      out[#out + 1] = "list_cockpit_params=" .. (ok and type(v) or "error")
    end
  else
    out[#out + 1] = "list_cockpit_params=missing"
  end
  local s = table.concat(out, " ")
  if s ~= SQE_ECM.probe_last then
    SQE_ECM.probe_last = s
    SQE_ECM.probe_n = SQE_ECM.probe_n + 1
    pcall(log.write, "SQE", log.INFO, "SQE EXPORT probe: " .. tostring(SQE_ECM.name) .. " t=" .. string.format("%.0f", t) .. " " .. s)
  end
end

function LuaExportStart()
  if prev_start then pcall(prev_start) end
  local ok, n = pcall(function() return LoGetSelfData().Name end)
  SQE_ECM.name = ok and n or nil
  SQE_ECM.next_t = 0; SQE_ECM.last = nil; SQE_ECM.last_w = -10; SQE_ECM.probe_t = 0; SQE_ECM.probe_last = nil; SQE_ECM.probe_n = 0; SQE_ECM.params = nil; SQE_ECM.pn = 0
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
    if not (j and j.enabled) then pcall(probe, t) end
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
