import 'package:flutter/material.dart';
import 'package:flutter_overlay_window/flutter_overlay_window.dart';
import 'package:flutter_colorpicker/flutter_colorpicker.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:pdf/pdf.dart' as pdf_lib;
import 'package:pdf/widgets.dart' as pw;
import 'package:path_provider/path_provider.dart';
import 'package:open_filex/open_filex.dart';
import 'dart:io';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const MyApp());
}

@pragma("vm:entry-point")
void overlayMain() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const MaterialApp(
    debugShowCheckedModeBanner: false,
    home: OnScreenPenOverlay(),
  ));
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'On-Screen Pen',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: Colors.blue, brightness: Brightness.dark),
        useMaterial3: true,
      ),
      home: const HomeScreen(),
    );
  }
}

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  bool _isOverlayRunning = false;

  @override
  void initState() {
    super.initState();
    _checkOverlayStatus();
  }

  Future<void> _checkOverlayStatus() async {
    final status = await FlutterOverlayWindow.isActive();
    setState(() {
      _isOverlayRunning = status;
    });
  }

  Future<void> _toggleOverlay() async {
    if (_isOverlayRunning) {
      await FlutterOverlayWindow.closeOverlay();
    } else {
      if (!await FlutterOverlayWindow.isPermissionGranted()) {
        final bool? granted = await FlutterOverlayWindow.requestPermission();
        if (granted != true) return;
      }
      
      await FlutterOverlayWindow.showOverlay(
        enableDrag: true,
        flag: OverlayFlag.clickThrough,
        alignment: OverlayAlignment.centerRight,
        visibility: NotificationVisibility.visibilityPublic,
        positionGravity: PositionGravity.right,
        height: 200, // Small starting bubble size
        width: 200,
      );
    }
    _checkOverlayStatus();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text("On-Screen Pen Mobile")),
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const Icon(Icons.edit_note, size: 80, color: Colors.blue),
            const SizedBox(height: 20),
            ElevatedButton.icon(
              onPressed: _toggleOverlay,
              icon: Icon(_isOverlayRunning ? Icons.stop : Icons.play_arrow),
              label: Text(_isOverlayRunning ? "Stop Pen Overlay" : "Start Pen Overlay"),
              style: ElevatedButton.styleFrom(padding: const EdgeInsets.symmetric(horizontal: 30, vertical: 15)),
            ),
            const SizedBox(height: 20),
            const Padding(
              padding: EdgeInsets.symmetric(horizontal: 40.0),
              child: Text(
                "When started, a small floating tool bubble will appear on the edge of your screen. Tap it to expand your drawing tools.",
                textAlign: TextAlign.center,
                style: TextStyle(color: Colors.grey),
              ),
            )
          ],
        ),
      ),
    );
  }
}

// ─── OVERLAY WIDGET ───
class OnScreenPenOverlay extends StatefulWidget {
  const OnScreenPenOverlay({super.key});

  @override
  State<OnScreenPenOverlay> createState() => _OnScreenPenOverlayState();
}

class _OnScreenPenOverlayState extends State<OnScreenPenOverlay> {
  bool isExpanded = false;
  bool isDrawingMode = false;
  bool isWhiteboardMode = false;
  String gridMode = "None"; // None, Lined, Dot Grid, Square
  
  List<DrawingPath> paths = [];
  DrawingPath? currentPath;
  Color activeColor = Colors.red;
  double activeThickness = 5.0;
  bool isEraser = false;

  void toggleExpansion() async {
    setState(() {
      isExpanded = !isExpanded;
    });
    
    if (isExpanded) {
      await FlutterOverlayWindow.resizeOverlay(WindowSize.matchParent, WindowSize.matchParent, false);
      // Wait a moment for resize, then make intractable
      await Future.delayed(const Duration(milliseconds: 100));
      await FlutterOverlayWindow.updateFlag(isDrawingMode ? OverlayFlag.defaultFlag : OverlayFlag.clickThrough);
    } else {
      await FlutterOverlayWindow.resizeOverlay(200, 200, true);
      await FlutterOverlayWindow.updateFlag(OverlayFlag.clickThrough); // Only the draggable bubble is interactive at the edges
      setState(() {
        isDrawingMode = false;
      });
    }
  }

  void toggleMode() {
    setState(() {
      isDrawingMode = !isDrawingMode;
      FlutterOverlayWindow.updateFlag(isDrawingMode ? OverlayFlag.defaultFlag : OverlayFlag.clickThrough);
    });
  }

  void pickColor() {
    showDialog(
      context: context,
      builder: (BuildContext context) {
        return AlertDialog(
          title: const Text('Pick a color'),
          content: SingleChildScrollView(
            child: BlockPicker(
              pickerColor: activeColor,
              onColorChanged: (color) {
                setState(() {
                  activeColor = color;
                  isEraser = false;
                });
              },
            ),
          ),
          actions: [
            TextButton(child: const Text('Done'), onPressed: () => Navigator.of(context).pop()),
          ],
        );
      },
    );
  }

  Future<void> exportPdf() async {
    final pdf = pw.Document();
    
    pdf.addPage(
      pw.Page(
        pageFormat: pdf_lib.PdfPageFormat.a4,
        build: (pw.Context context) {
          return pw.FullPage(
            ignoreMargins: true,
            child: pw.CustomPaint(
              size: const pdf_lib.PdfPoint(595, 842), // standard A4
              painter: PdfDrawingPainter(paths: paths, isWhiteboard: isWhiteboardMode, gridType: gridMode),
            ),
          );
        },
      ),
    );

    try {
      final directory = await getExternalStorageDirectory();
      final file = File('${directory!.path}/onscreen_notes_${DateTime.now().millisecondsSinceEpoch}.pdf');
      await file.writeAsBytes(await pdf.save());
      
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Saved to ${file.path}')));
      OpenFilex.open(file.path);
    } catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text('Export failed: $e')));
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!isExpanded) {
      return SafeArea(
        child: Align(
          alignment: Alignment.centerRight,
          child: GestureDetector(
            onTap: toggleExpansion,
            child: Container(
              margin: const EdgeInsets.only(right: 16),
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: Colors.blueAccent.withValues(alpha: 0.9),
                shape: BoxShape.circle,
                boxShadow: const [BoxShadow(blurRadius: 10, color: Colors.black45)],
              ),
              child: const Icon(Icons.edit, color: Colors.white, size: 30),
            ),
          ),
        ),
      );
    }

    return Material(
      color: Colors.transparent,
      child: Stack(
        children: [
          // Background solid color or transparent layer
          if (isWhiteboardMode && isDrawingMode)
            Container(color: Colors.white)
          else if (isDrawingMode)
            Container(color: Colors.transparent),

          // Transparent Drawing Canvas
          if (isDrawingMode)
            GestureDetector(
              onPanStart: (details) {
                setState(() {
                  currentPath = DrawingPath(
                    points: [details.globalPosition],
                    color: isEraser ? (isWhiteboardMode ? Colors.white : Colors.transparent) : activeColor,
                    thickness: isEraser ? activeThickness * 4 : activeThickness,
                    isEraser: isEraser,
                  );
                });
              },
              onPanUpdate: (details) {
                setState(() {
                  currentPath?.points.add(details.globalPosition);
                });
              },
              onPanEnd: (_) {
                setState(() {
                  if (currentPath != null) paths.add(currentPath!);
                  currentPath = null;
                });
              },
              child: CustomPaint(
                painter: DrawingPainter(
                  paths: paths, 
                  currentPath: currentPath, 
                  gridType: gridMode,
                  isWhiteboard: isWhiteboardMode,
                ),
                size: Size.infinite,
              ),
            ),

          // UI Layer
          SafeArea(
            child: Align(
              alignment: Alignment.topRight,
              child: Container(
                margin: const EdgeInsets.all(16.0),
                padding: const EdgeInsets.all(12.0),
                decoration: BoxDecoration(
                  color: Colors.grey.shade900.withValues(alpha: 0.95),
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(color: Colors.white24),
                  boxShadow: const [BoxShadow(blurRadius: 8, color: Colors.black54)]
                ),
                width: 250,
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        const Text("OnScreen Pen", style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
                        InkWell(
                          onTap: toggleExpansion,
                          child: const Icon(Icons.close, color: Colors.grey),
                        )
                      ],
                    ),
                    const Divider(color: Colors.white24),
                    
                    // Main Toggle
                    SizedBox(
                      width: double.infinity,
                      child: ElevatedButton.icon(
                        style: ElevatedButton.styleFrom(
                          backgroundColor: isDrawingMode ? Colors.blueAccent : Colors.grey.shade700,
                          foregroundColor: Colors.white,
                        ),
                        onPressed: toggleMode,
                        icon: Icon(isDrawingMode ? Icons.edit : Icons.mouse),
                        label: Text(isDrawingMode ? "Draw Mode" : "Mouse Mode"),
                      ),
                    ),
                    
                    if (isDrawingMode) ...[
                       const SizedBox(height: 10),
                       Row(
                         mainAxisAlignment: MainAxisAlignment.spaceAround,
                         children: [
                           IconButton(
                             icon: Icon(Icons.color_lens, color: activeColor),
                             onPressed: pickColor,
                             tooltip: "Color",
                           ),
                           IconButton(
                             icon: Icon(Icons.cleaning_services, color: isEraser ? Colors.red : Colors.white),
                             onPressed: () => setState(() => isEraser = !isEraser),
                             tooltip: "Eraser",
                           ),
                           IconButton(
                             icon: const Icon(Icons.undo, color: Colors.white),
                             onPressed: () => setState(() { if(paths.isNotEmpty) paths.removeLast(); }),
                             tooltip: "Undo",
                           ),
                           IconButton(
                             icon: const Icon(Icons.delete, color: Colors.white),
                             onPressed: () => setState(() => paths.clear()),
                             tooltip: "Clear All",
                           ),
                         ],
                       ),
                       const SizedBox(height: 5),
                       Slider(
                         value: activeThickness,
                         min: 1.0,
                         max: 30.0,
                         activeColor: Colors.blueAccent,
                         onChanged: (val) => setState(() => activeThickness = val),
                       ),
                       
                       const Divider(color: Colors.white24),
                       // Settings
                       Row(
                         mainAxisAlignment: MainAxisAlignment.spaceBetween,
                         children: [
                           const Text("Whiteboard", style: TextStyle(color: Colors.white70, fontSize: 13)),
                           Switch(
                             value: isWhiteboardMode,
                             onChanged: (val) => setState(() => isWhiteboardMode = val),
                             activeColor: Colors.blueAccent,
                           )
                         ],
                       ),
                       Row(
                         mainAxisAlignment: MainAxisAlignment.spaceBetween,
                         children: [
                           const Text("Grid", style: TextStyle(color: Colors.white70, fontSize: 13)),
                           DropdownButton<String>(
                             value: gridMode,
                             dropdownColor: Colors.grey.shade800,
                             style: const TextStyle(color: Colors.white, fontSize: 13),
                             items: ["None", "Lined", "Dot Grid", "Square"]
                               .map((e) => DropdownMenuItem(value: e, child: Text(e))).toList(),
                             onChanged: (v) => setState(() => gridMode = v!),
                             underline: const SizedBox(),
                           )
                         ],
                       ),
                    ],
                    const Divider(color: Colors.white24),
                    SizedBox(
                       width: double.infinity,
                       child: TextButton.icon(
                         style: TextButton.styleFrom(foregroundColor: Colors.redAccent),
                         onPressed: exportPdf,
                         icon: const Icon(Icons.picture_as_pdf),
                         label: const Text("Export PDF"),
                       ),
                    )
                  ],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class DrawingPath {
  final List<Offset> points;
  final Color color;
  final double thickness;
  final bool isEraser;
  DrawingPath({required this.points, required this.color, required this.thickness, this.isEraser = false});
}

class DrawingPainter extends CustomPainter {
  final List<DrawingPath> paths;
  final DrawingPath? currentPath;
  final String gridType;
  final bool isWhiteboard;

  DrawingPainter({required this.paths, this.currentPath, this.gridType = "None", this.isWhiteboard = false});

  @override
  void paint(Canvas canvas, Size size) {
    // Draw Grid
    if (gridType != "None") {
      final paint = Paint()..color = (isWhiteboard ? Colors.black12 : Colors.white24)..strokeWidth = 1;
      const step = 40.0;
      
      if (gridType == "Lined") {
        for (double y = step; y < size.height; y += step) canvas.drawLine(Offset(0, y), Offset(size.width, y), paint);
        canvas.drawLine(const Offset(80, 0), Offset(80, size.height), Paint()..color = Colors.red.withValues(alpha: 0.5)..strokeWidth = 2);
      } else if (gridType == "Dot Grid") {
        final dotPaint = Paint()..color = (isWhiteboard ? Colors.black26 : Colors.white30)..strokeWidth = 3..strokeCap = StrokeCap.round;
        for (double x = step; x < size.width; x += step) {
          for (double y = step; y < size.height; y += step) canvas.drawPoint(Offset(x, y), dotPaint);
        }
      } else if (gridType == "Square") {
        for (double x = step; x < size.width; x += step) canvas.drawLine(Offset(x, 0), Offset(x, size.height), paint);
        for (double y = step; y < size.height; y += step) canvas.drawLine(Offset(0, y), Offset(size.width, y), paint);
      }
    }

    // Draw Paths
    for (var path in paths) {
      _drawSmoothPath(canvas, path);
    }
    if (currentPath != null) {
      _drawSmoothPath(canvas, currentPath!);
    }
  }

  void _drawSmoothPath(Canvas canvas, DrawingPath path) {
    if (path.points.isEmpty) return;
    
    final paint = Paint()
      ..color = path.color
      ..strokeWidth = path.thickness
      ..strokeCap = StrokeCap.round
      ..strokeJoin = StrokeJoin.round
      ..style = PaintingStyle.stroke;
      
    if (path.isEraser && !isWhiteboard) {
      paint.blendMode = BlendMode.clear;
    }

    final p = Path();
    p.moveTo(path.points[0].dx, path.points[0].dy); // FIX: dy instead of dx
    if(path.points.length == 1) {
       p.lineTo(path.points[0].dx + 0.1, path.points[0].dy + 0.1);
    } else {
      for (int i = 1; i < path.points.length - 1; i++) {
        final double xc = (path.points[i].dx + path.points[i + 1].dx) / 2;
        final double yc = (path.points[i].dy + path.points[i + 1].dy) / 2;
        p.quadraticBezierTo(path.points[i].dx, path.points[i].dy, xc, yc);
      }
      p.lineTo(path.points.last.dx, path.points.last.dy);
    }
    
    canvas.drawPath(p, paint);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => true;
}


// PDF EXPORT PAINTER
class PdfDrawingPainter extends pw.CustomPainter {
  final List<DrawingPath> paths;
  final bool isWhiteboard;
  final String gridType;

  PdfDrawingPainter({required this.paths, required this.isWhiteboard, required this.gridType});

  @override
  void paint(pw.Context context, pw.Vec size) {
    final canvas = context.canvas;
    
    // Draw background
    if (isWhiteboard) {
      canvas.drawRect(0, 0, size.x, size.y);
      canvas.setFillColor(pdf_lib.PdfColors.white);
      canvas.fillPath();
    }

    // Draw Grid
    if (gridType != "None") {
      final color = isWhiteboard ? pdf_lib.PdfColors.grey300 : pdf_lib.PdfColors.grey700;
      const step = 40.0;
      
      canvas.setStrokeColor(color);
      canvas.setLineWidth(1);
      
      if (gridType == "Lined") {
        for (double y = step; y < size.y; y += step) {
          canvas.drawLine(0, size.y - y, size.x, size.y - y);
          canvas.strokePath();
        }
      } else if (gridType == "Square") {
        for (double x = step; x < size.x; x += step) { canvas.drawLine(x, 0, x, size.y); canvas.strokePath(); }
        for (double y = step; y < size.y; y += step) { canvas.drawLine(0, y, size.x, y); canvas.strokePath(); }
      }
    }

    // Draw Paths
    for (var path in paths) {
      if (path.points.isEmpty) continue;
      if (path.isEraser) continue; // Skip erasers on transparent PDFs
      
      final c0 = path.color;
      final pdfColor = pdf_lib.PdfColor(c0.r / 255, c0.g / 255, c0.b / 255, c0.a / 255);
      
      canvas.setStrokeColor(pdfColor);
      canvas.setLineWidth(path.thickness);
      canvas.setLineCap(pdf_lib.PdfLineCap.round);
      canvas.setLineJoin(pdf_lib.PdfLineJoin.round);

      // Map Android coordinates (0,0 is top-left) to PDF coordinates (0,0 is bottom-left)
      double mapY(double y) => size.y - y;

      canvas.moveTo(path.points[0].dx, mapY(path.points[0].dy));
      if(path.points.length == 1) {
         canvas.lineTo(path.points[0].dx + 0.1, mapY(path.points[0].dy + 0.1));
      } else {
        for (int i = 1; i < path.points.length - 1; i++) {
          canvas.lineTo(path.points[i].dx, mapY(path.points[i].dy));
        }
        canvas.lineTo(path.points.last.dx, mapY(path.points.last.dy));
      }
      canvas.strokePath();
    }
  }
}
