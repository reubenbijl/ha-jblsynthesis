# JBL Synthesis for Home Assistant

Control a JBL Synthesis **SDR-35**, **SDR-38**, **SDP-55** or **SDP-58** from Home
Assistant over its IP control interface. These units are JBL's builds of the Arcam HDA
platform, and this integration drives them through a fork of the
[arcam-fmj](https://github.com/elupus/arcam_fmj) library carrying the JBL Synthesis
additions (model recognition, the Logic 16 Immersion decode mode, and General Setup /
Engineering Menu decoding) until they are merged upstream.

## What you get

| Entity | What it does |
| --- | --- |
| Media player | Power, volume (set and step), mute, input selection, and decode-mode selection — including Logic 16 Immersion, with the mode list tracking whether the incoming stream is stereo or multi-channel |
| Room EQ select | Which Dirac Live calibration slot is active, using the slot names stored on the receiver |
| Audio format sensor | The incoming stream as the front panel words it, e.g. `Dolby Atmos` or `DTS-HD Master Audio 3/4.1` |
| Input name sensor | The user-assigned name of the current input |
| Incoming video sensor | e.g. `3840x2160p60 (Dolby Vision)` |
| Sample rate, bitrate, dialogue normalisation | Stream diagnostics |

Diagnostics download and full unit-test coverage are included; the quality bar is
tracked rule-by-rule in
[`quality_scale.yaml`](custom_components/jblsynthesis/quality_scale.yaml).

## Requirements on the receiver

- **IP control enabled**: General Setup → Control → On (or via RS232: hold the front
  panel DIRECT button for four seconds). Off is the factory default.
- **Network on in standby** if you want to power the unit on from Home Assistant. In
  deep standby the receiver leaves the network entirely — nothing can wake it over IP,
  and the integration shows its entities as unavailable until it returns.

## Installation

### HACS

1. HACS → Integrations → ⋮ → *Custom repositories*.
2. Add `https://github.com/reubenbijl/ha-jblsynthesis` as an *Integration*.
3. Install **JBL Synthesis**, then restart Home Assistant.

### Manual

Copy `custom_components/jblsynthesis` into your Home Assistant `config/custom_components`
directory and restart.

## Configuration

Settings → Devices & Services → *Add Integration* → **JBL Synthesis**.

| Field | Meaning |
| --- | --- |
| Host | The receiver's hostname or IP address, shown on the unit under Network Settings |
| Port | The IP control port — 50000 unless you have changed it |

The receiver must be awake while you add it: the flow identifies the unit over the
control connection (make and model) before creating the entry. If the address later
changes, use *Reconfigure* on the entry rather than deleting it, so entities and
history are kept.

## How data flows

This is a push integration. One TCP connection stays open; the receiver reports every
state change on it (volume turned on the front panel included), and the library also
cycles through status requests on the same connection. Home Assistant polls nothing.
If the connection drops — deep standby, mains off, network blip — the integration
retries every ten seconds and logs once on the way down and once on recovery.

## Replacing a Node-RED dashboard card

The media player replaces power/volume/input buttons one-for-one. A minimal example
mirroring a typical receiver card:

```yaml
type: vertical-stack
cards:
  - type: media-control
    entity: media_player.sdr_35
  - type: entities
    entities:
      - sensor.sdr_35_audio_format
      - sensor.sdr_35_input_name
      - sensor.sdr_35_incoming_video
      - select.sdr_35_room_eq
```

Scripted actions use the standard media player services, e.g. "volume to 45" is:

```yaml
action: media_player.volume_set
target:
  entity_id: media_player.sdr_35
data:
  volume_level: 0.4545   # 45 on the receiver's 0-99 scale
```

## Known limitations

- **Deep standby is unreachable.** With *Network on in standby* disabled, powering on
  from Home Assistant is impossible over IP; use IR or enable that setting.
- **Zone 1 only** for now. The hardware supports a second zone; support is planned once
  the single-zone integration has soaked.
- The decode-mode list depends on the incoming stream, so a mode you can see on the
  remote may be absent until the stream type matches.

## Troubleshooting

- *Config flow says it cannot connect*: confirm the receiver is awake, IP control is
  enabled on the unit, and port 50000 is right.
- *Everything shows unavailable*: the connection is down — almost always deep standby.
  The integration reconnects by itself when the receiver returns.
- *Command rejected errors*: the receiver answers commands it cannot currently apply
  (for example during setup-menu use) with an error; the message carries the
  receiver's answer code.

## Removal

Settings → Devices & Services → JBL Synthesis → ⋮ → *Delete*. Then remove the
repository from HACS (or delete `custom_components/jblsynthesis` if installed
manually).
