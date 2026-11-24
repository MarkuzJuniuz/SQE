-- SQE FRAME LOG (installed by SQE)
-- A DCS hook that logs how long each simulation frame takes. SQE copies it to Saved Games\DCS\Scripts\Hooks and Saved Games\DCS_Server\Scripts\Hooks
-- ONLY when the environment variable SQE_DEBUG is 1, and takes it out again when it is not. The file also checks the variable itself: with SQE_DEBUG unset
-- or anything but 1 it does nothing at all (no callback is registered).
-- Writes to dcs.log:
--   "S89F summary ..." every 10 s of real time: frames, average FPS, worst frame in ms, frames over 25 / 50 / 100 ms, model time
--   "S89F hitch ..."   for every single frame longer than 50 ms (real time between two simulation frames), with the model time
-- A pause (model time standing still for more than a second) restarts the window. Needs nothing from the mission.

local env_ok, env_value = pcall(function() return os.getenv("SQE_DEBUG") end)
if not (env_ok and env_value == "1") then
    return
end

local S89F = {}
local lastReal, lastModel = nil, nil
local winStart, frames, worst, n25, n50, n100 = nil, 0, 0, 0, 0, 0

local function w(msg)
    log.write("S89F", log.INFO, msg)
end

function S89F.onSimulationStart()
    lastReal, lastModel, winStart = nil, nil, nil
    frames, worst, n25, n50, n100 = 0, 0, 0, 0, 0
    w("start")
end

function S89F.onSimulationFrame()
    local real, model = DCS.getRealTime(), DCS.getModelTime()
    if lastReal == nil then
        lastReal, lastModel, winStart = real, model, real
        return
    end
    local dt = real - lastReal
    local moved = model > lastModel
    lastReal, lastModel = real, model
    if not moved and dt > 1.0 then
        winStart, frames, worst, n25, n50, n100 = real, 0, 0, 0, 0, 0      -- paused (model time stood still over a second): restart the window
        return
    end
    -- (a frame that does not move model time at very high FPS still counts: the first version skipped them and then never reached a 10 s window)
    frames = frames + 1
    if dt > worst then worst = dt end
    if dt > 0.025 then n25 = n25 + 1 end
    if dt > 0.05 then
        n50 = n50 + 1
        w(string.format("hitch %.0f ms at model t=%.1f", dt * 1000, model))
    end
    if dt > 0.1 then n100 = n100 + 1 end
    local span = real - winStart
    if span >= 10 then
        w(string.format("summary t=%.0f frames=%d fps=%.1f worst=%.0f ms over25=%d over50=%d over100=%d", model, frames, frames / span, worst * 1000, n25, n50, n100))
        winStart, frames, worst, n25, n50, n100 = real, 0, 0, 0, 0, 0
    end
end

DCS.setUserCallbacks(S89F)
