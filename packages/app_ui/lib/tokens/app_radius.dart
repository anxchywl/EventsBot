import 'package:flutter/material.dart';

/// Revolut-style border radius constants for the redesigned home screen.
abstract class HomeRadius {
  static const double card = 20.0;
  static const double cardLg = 24.0;
  static const double button = 16.0;
  static const double pill = 100.0;
  static const double navIndicator = 100.0;
  static const double circle = 100.0;

  static BorderRadius get cardBR => BorderRadius.circular(card);
  static BorderRadius get cardLgBR => BorderRadius.circular(cardLg);
  static BorderRadius get buttonBR => BorderRadius.circular(button);
  static BorderRadius get pillBR => BorderRadius.circular(pill);
  static BorderRadius get circleBR => BorderRadius.circular(circle);
}
