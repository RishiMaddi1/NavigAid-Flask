// lib/main.dart
import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:camera/camera.dart';
import 'package:record/record.dart'; // AudioRecorder, RecordConfig, AudioEncoder
import 'package:flutter_tts/flutter_tts.dart';
import 'package:audioplayers/audioplayers.dart';
import 'package:http/http.dart' as http;
import 'package:path_provider/path_provider.dart';
import 'package:permission_handler/permission_handler.dart';

// A Riverpod provider to hold the vision context string
final imageContextProvider = StateProvider<String?>((ref) => null);

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final cameras = await availableCameras();
  runApp(
    ProviderScope(
      child: MyApp(cameras: cameras),
    ),
  );
}

class MyApp extends StatelessWidget {
  final List<CameraDescription> cameras;
  const MyApp({required this.cameras, Key? key}) : super(key: key);

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Nav Aid',
      theme: ThemeData(
        colorScheme: ColorScheme.light(
          primary: Color(0xFF005FCC),
          secondary: Color(0xFFFFC400),
        ),
        appBarTheme: AppBarTheme(
          backgroundColor: Color(0xFF005FCC),
          foregroundColor: Colors.white,
        ),
        elevatedButtonTheme: ElevatedButtonThemeData(
          style: ElevatedButton.styleFrom(
            backgroundColor: Color(0xFF005FCC),
            foregroundColor: Color(0xFFFFC400),
            textStyle: TextStyle(fontSize: 24, fontWeight: FontWeight.bold),
          ),
        ),
      ),
      home: AnalyzeScreen(cameras: cameras),
    );
  }
}

/// SCREEN 1: live camera preview + capture button
class AnalyzeScreen extends ConsumerStatefulWidget {
  final List<CameraDescription> cameras;
  const AnalyzeScreen({required this.cameras, Key? key}) : super(key: key);

  @override
  ConsumerState<AnalyzeScreen> createState() => _AnalyzeScreenState();
}

class _AnalyzeScreenState extends ConsumerState<AnalyzeScreen> {
  late CameraController _controller;
  bool _ready = false;
  final FlutterTts _tts = FlutterTts();

  @override
  void initState() {
    super.initState();
    _requestCameraPermission();
    _controller = CameraController(
      widget.cameras[0],
      ResolutionPreset.medium,
      enableAudio: false,
    );
    _initCamera();
  }

  Future<void> _requestCameraPermission() async {
    final status = await Permission.camera.request();
    if (!status.isGranted) {
      await _tts.speak("Camera permission denied. Please enable it in settings.");
    }
  }

  Future<void> _initCamera() async {
    await _controller.initialize();
    if (!mounted) return;
    setState(() => _ready = true);
    ref.read(imageContextProvider.notifier).state = null;
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  Future<void> _captureAndAnalyze() async {
    if (!_ready) return;
    try {
      await _tts.speak("Capturing image");
      final XFile file = await _controller.takePicture();
      print("Captured image to: ${file.path}");

      final uri = Uri.parse('https://navigaid-flask.onrender.com/analyze_image');
      final req = http.MultipartRequest('POST', uri)
        ..files.add(await http.MultipartFile.fromPath('image', file.path));
      print("Sending analyze_image request...");
      final streamed = await req.send();
      print("Response status: ${streamed.statusCode}");

      if (streamed.statusCode == 200) {
        final res = await http.Response.fromStream(streamed);
        final data = json.decode(res.body) as Map<String, dynamic>;
        final visionContext = data['context'] as String?;
        ref.read(imageContextProvider.notifier).state = visionContext;
        print("Received context: $visionContext");

        await _tts.speak("Image analyzed. Moving on.");
        if (!mounted) return;
        Navigator.push(
          context,
          MaterialPageRoute(builder: (_) => AskScreen()),
        );
      } else {
        await _tts.speak("Analyze failed, status ${streamed.statusCode}");
      }
    } catch (e, st) {
      print("Error capturing or analyzing: $e\n$st");
      await _tts.speak("Error capturing or analyzing");
    }
  }

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(title: Text('Capture', style: TextStyle(color: cs.onPrimary))),
      body: _ready
          ? Stack(
              children: [
                CameraPreview(_controller),
                Positioned.fill(
                  child: Center(
                    child: ElevatedButton(
                      onPressed: _captureAndAnalyze,
                      child: Text('Capture'),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: cs.primary.withOpacity(0.7),
                        foregroundColor: cs.secondary,
                        shape: CircleBorder(),
                        minimumSize: Size(200, 200),
                      ),
                    ),
                  ),
                ),
              ],
            )
          : Center(child: CircularProgressIndicator()),
    );
  }
}

/// SCREEN 2: one big button toggles record → stop+send → play
class AskScreen extends ConsumerStatefulWidget {
  const AskScreen({Key? key}) : super(key: key);

  @override
  ConsumerState<AskScreen> createState() => _AskScreenState();
}

class _AskScreenState extends ConsumerState<AskScreen> {
  final AudioRecorder _recorder = AudioRecorder();
  final AudioPlayer   _player   = AudioPlayer();
  final FlutterTts    _tts      = FlutterTts();

  bool    _isRecording = false;
  String? _audioPath;

  /// Starts or stops recordings on each tap
  Future<void> _toggleRecording() async {
    if (!_isRecording) {
      // 1️⃣ REQUEST MIC PERMISSION
      if (!await Permission.microphone.request().isGranted) {
        await _tts.speak("Microphone permission denied");
        return;
      }

      // 2️⃣ START RECORDING TO A WAV FILE
      final dir  = await getTemporaryDirectory();
      final path = '${dir.path}/question.wav';
      await _recorder.start(
        const RecordConfig(encoder: AudioEncoder.wav),
        path: path,
      );

      setState(() { 
        _isRecording = true; 
        _audioPath   = path; 
      });

      // 3️⃣ DEBUG: print stored vision context
      final ctx = ref.read(imageContextProvider) ?? '<no context>';
      print("🔴 Recording started. Context: $ctx");

    } else {
      // 4️⃣ STOP RECORDING
      final path = await _recorder.stop();
      setState(() => _isRecording = false);
      print("⏹ Recording stopped. File: $path");

      // 5️⃣ SEND CONTEXT + AUDIO TO BACKEND
      final ctx = ref.read(imageContextProvider) ?? '';
      print("📤 Sending context to API: $ctx");

      final uri = Uri.parse('https://navigaid-flask.onrender.com/ask_question');
      final req = http.MultipartRequest('POST', uri)
        ..fields['context'] = ctx
        ..files.add(await http.MultipartFile.fromPath('audio', path!));

      final streamed = await req.send();
      print("🔁 ask_question status: ${streamed.statusCode}");
      
      // collect full response once and inspect headers/body
      final res = await http.Response.fromStream(streamed);
      final contentType = res.headers['content-type'] ?? '';
      print("ask_question content-type: $contentType");
      
      if (streamed.statusCode == 200 && contentType.contains('audio')) {
        final bytes = res.bodyBytes;
        print("▶️ Playing audio, ${bytes.length} bytes");
        try {
          await _player.play(
            BytesSource(bytes, mimeType: 'audio/mpeg'),
          );
        } catch (err) {
          print("Audio playback failed: $err");
          await _tts.speak("Playback error.");
        }
      } else {
        // either a 500 or we got JSON/HTML instead of audio
        final errorMsg = res.body;
        print("❗ Server error response body:\n$errorMsg");
        await _tts.speak("Server error. Check logs.");
      }
    }
  }

  @override
  void dispose() {
    _recorder.dispose();
    _player.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SizedBox.expand(
        child: ElevatedButton(
          onPressed: _toggleRecording,
          child: Text(
            _isRecording ? 'Stop listening & Send' : 'Press to listen to your question',
            style: TextStyle(fontSize: 24),
          ),
          style: ElevatedButton.styleFrom(padding: EdgeInsets.zero),
        ),
      ),
    );
  }
}