import 'dart:typed_data';

/// Wraps raw little-endian 16-bit PCM samples in a WAV (RIFF) header, the format
/// the backend accepts for voice turns.
Uint8List wavFromPcm16(Uint8List pcm, {required int sampleRate, int channels = 1}) {
  const bitsPerSample = 16;
  final byteRate = sampleRate * channels * bitsPerSample ~/ 8;
  final header = ByteData(44)
    ..setUint32(0, 0x52494646) // "RIFF"
    ..setUint32(4, 36 + pcm.length, Endian.little)
    ..setUint32(8, 0x57415645) // "WAVE"
    ..setUint32(12, 0x666d7420) // "fmt "
    ..setUint32(16, 16, Endian.little) // PCM chunk size
    ..setUint16(20, 1, Endian.little) // PCM format
    ..setUint16(22, channels, Endian.little)
    ..setUint32(24, sampleRate, Endian.little)
    ..setUint32(28, byteRate, Endian.little)
    ..setUint16(32, channels * bitsPerSample ~/ 8, Endian.little)
    ..setUint16(34, bitsPerSample, Endian.little)
    ..setUint32(36, 0x64617461) // "data"
    ..setUint32(40, pcm.length, Endian.little);
  return (BytesBuilder(copy: false)
        ..add(header.buffer.asUint8List())
        ..add(pcm))
      .takeBytes();
}

/// Length of [pcm] (16-bit samples) in time.
Duration pcm16Duration(int byteLength, {required int sampleRate, int channels = 1}) =>
    Duration(microseconds: byteLength * 1000000 ~/ (sampleRate * channels * 2));
