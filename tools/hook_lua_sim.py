"""tools/hook_lua_sim.py (v0.41.217): runs the mission hook (sqe/debrief.py lua_hook) under lupa with a stubbed DCS API and fires fake blue events (hit, eject, dead, crash)
at it. Catches what `load()` cannot: a local declared further down the file than the event handler that reads it ("attempt to index global 'DMGL'", XO's 2026-10-30
script error), and any undefined global the hook reads. Needs `pip install lupa`; the smoke check skips without it.

    run(lua_source) -> "ok | undefined globals read: <none> | said: <the radio lines the stub saw>"  or  "COMPILE: / RUN: / EVENT ERRORS: <message>"
"""
DRIVER = r'''
local src, ALLOWED = ...
local reads, said_ = {}, {}
local stub; stub = setmetatable({}, {__index = function(t,k) return stub end, __call = function() return stub end})
local ev, n = {}, 0
setmetatable(ev, {__index = function(t,k) n = n + 1; rawset(t,k,n); return n end})
local handler
local unit = function(name) return setmetatable({getName = function() return name end, isExist = function() return true end, inAir = function() return true end,
   getCoalition = function() return 2 end, getPoint = function() return {x=0,y=0,z=0} end, getGroup = function() return {getName=function() return "g" end, getID=function() return 1 end} end,
   getTypeName = function() return "FA-18C_hornet" end, hasAttribute = function() return false end, getLife = function() return 1 end, getDesc = function() return {} end}, {__index = function() return function() return nil end end}) end
local env = {}
local base = {env=true, world=true, timer=true, trigger=true, coalition=true, Group=true, Unit=true, Object=true, lfs=true, io=true, os=true, math=true, string=true, table=true,
  pcall=true, ipairs=true, pairs=true, tostring=true, tonumber=true, next=true, type=true, select=true, land=true, missionCommands=true, StaticObject=true, Airbase=true,
  SceneryObject=true, net=true, atmosphere=true, require=true, error=true, assert=true, setmetatable=true, getmetatable=true, unpack=true, print=true, rawset=true, rawget=true, xpcall=true, loadstring=true, load=true, _G=true, AI=true, Weapon=true, country=true, radio=true, a_do_script=true}
setmetatable(env, {__index = function(t,k) if not base[k] then reads[k] = true end; return nil end})
env._G = env
env.math, env.string, env.table, env.pcall, env.ipairs, env.pairs, env.tostring, env.tonumber, env.next, env.type, env.select = math, string, table, pcall, ipairs, pairs, tostring, tonumber, next, type, select
env.setmetatable, env.getmetatable, env.error, env.assert, env.rawset, env.rawget, env.unpack = setmetatable, getmetatable, error, assert, rawset, rawget, unpack or table.unpack
env.os = {time = function() return 0 end, date = function() return "" end, clock = function() return 0 end}
env.io = {open = function() return nil end}
env.lfs = setmetatable({writedir = function() return "C:\\tmp\\" end}, {__index = function() return function() return nil end end})
env.env = {info = function() end, warning = function() end, error = function() end}
env.timer = {getTime = function() return 100 end, getAbsTime = function() return 100 end, scheduleFunction = function() return 1 end}
env.trigger = {action = setmetatable({}, {__index = function() return function(...) local a = {...}; for _, v in ipairs(a) do if type(v) == "string" and v ~= "" then said_[#said_+1] = v end end end end}), misc = {getUserFlag = function() return 1 end, setUserFlag = function() end}}
env.world = {event = ev, addEventHandler = function(h) handler = h end}
env.coalition = {side = {RED = 1, BLUE = 2}, getGroups = function() return {} end}
env.Group = {Category = {AIRPLANE = 0}, getByName = function() return {getID = function() return 1 end, getUnits = function() return {} end, getUnit = function() return unit("Viper 1-1") end} end}
env.Unit = {getByName = function(n) return unit(n) end}
env.Object = {Category = {UNIT = 1, STATIC = 3}}
env.StaticObject = {getByName = function() return nil end}
env.missionCommands = {addCommandForGroup = function() end}
env.land = {getHeight = function() return 0 end}
env.net = {}
local fn, err = load(src, "hook", "t", env)
if not fn then return "COMPILE: " .. tostring(err) end
local ok, e1 = pcall(fn)
if not ok then return "RUN: " .. tostring(e1) end
local errs = {}
local function fire(t) local ok2, e2 = pcall(function() handler:onEvent(t) end); if not ok2 then errs[#errs+1] = tostring(e2) end end
local ids = {hit = ev.S_EVENT_HIT, dead = ev.S_EVENT_DEAD, ej = ev.S_EVENT_EJECTION, crash = ev.S_EVENT_CRASH, shot = ev.S_EVENT_SHOT, kill = ev.S_EVENT_KILL, land = ev.S_EVENT_LAND, take = ev.S_EVENT_TAKEOFF}
for _, who in ipairs({"Viper 1-2", "Magic 1-1"}) do
  fire({id = ids.hit, initiator = unit("Mig 1"), target = unit(who), weapon = nil})
  fire({id = ids.ej, initiator = unit(who)})
  fire({id = ids.dead, initiator = unit(who)})
  fire({id = ids.crash, initiator = unit(who)})
end
local missing = {}
for k in pairs(reads) do missing[#missing+1] = k end
table.sort(missing)
return (#errs > 0 and ("EVENT ERRORS: " .. table.concat(errs, " | ")) or "ok") .. " | undefined globals read: " .. table.concat(missing, ",") .. " | said: " .. table.concat(said_, " ## ")
'''


def run(src: str) -> str:
    import lupa
    rt = lupa.LuaRuntime(unpack_returned_tuples=True)
    return rt.eval("function(d) return load(d) end")(DRIVER)(src, None)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, ".")
    from sqe import debrief as db
    print(run(db.lua_hook("c", 1, "p", [], "Viper 1-1", "Viper 1", flights={"Viper 1-2": "VIPER 1-2"}, tune_flags=[9101], tune_mhz=262.5, awacs_unit="Magic 1-1",
                          dmg={"Viper 1-2": "VIPER 1-2", "Magic 1-1": "*MAGIC"}, dmg_on=True, awacs="Magic")))
