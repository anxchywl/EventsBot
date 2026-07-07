/// A selectable event category returned by the backend.
class CategoryModel {
  final int id;
  final String name;
  final String slug;

  const CategoryModel({
    required this.id,
    required this.name,
    required this.slug,
  });

  factory CategoryModel.fromJson(Map<String, dynamic> json) {
    return CategoryModel(
      id: json['id'] as int,
      name: json['name'] as String,
      slug: json['slug'] as String,
    );
  }
}
