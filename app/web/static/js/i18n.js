import { state } from "./state.js";

const dict = {
  en: {
    events: "Events",
    favorites: "Favorites",
    reminders: "Reminders",
    categories: "Categories",
    profile: "Profile",
    unavailable: "Event no longer available.",
    loading: "Loading",
    dateTime: "Date & time",
    location: "Location",
    organizer: "Organizer",
    attendees: "Attendees",
    description: "Description",
    related: "Related events",
    addReminder: "Add Reminder",
    share: "Share",
    register: "Register",
    backToEvents: "Back to Events",
    emptyFavorites: "No favorite events yet.",
    emptyReminders: "No upcoming reminders.",
    emptyEvents: "No events right now.",
    ended: "Ended",
    reminderTitle: "Notify me before the event",
    reminderTimer: "DD : HH : MM",
    reminderSetFor: "Notify me before the event",
    reminderZero: "Timer must be greater than zero.",
    reminderTooLate: "It's too late to set this reminder.",
    reminderDuplicate: "You already have a reminder at this time.",
    reminderRemoved: "Reminder removed.",
    save: "Save",
    cancel: "Cancel",
    remove: "Remove",
    success: "Reminder set!",
    invalidReminder: "Choose a valid time before the event.",
    authRequired: "Open this from Telegram to use this action.",
    career: "Career",
    computer_science: "Computer Science",
    hackathons: "Hackathons",
    workshops: "Workshops",
    sport: "Sport",
    volunteering: "Volunteering",
    entertainment: "Entertainment",
    club_events: "Club Events",
  },
  ru: {
    events: "События",
    favorites: "Избранное",
    reminders: "Напоминания",
    categories: "Категории",
    profile: "Профиль",
    unavailable: "Событие больше недоступно.",
    loading: "Загрузка",
    dateTime: "Дата и время",
    location: "Локация",
    organizer: "Организатор",
    attendees: "Участники",
    description: "Описание",
    related: "Похожие события",
    addReminder: "Напомнить",
    share: "Поделиться",
    register: "Регистрация",
    backToEvents: "К событиям",
    emptyFavorites: "Пока нет избранных событий.",
    emptyReminders: "Нет будущих напоминаний.",
    emptyEvents: "Событий пока нет.",
    ended: "Завершено",
    reminderTitle: "Напомнить до события",
    reminderTimer: "ДД : ЧЧ : ММ",
    reminderSetFor: "Напомнить до события",
    reminderZero: "Время должно быть больше нуля.",
    reminderTooLate: "Слишком поздно устанавливать это напоминание.",
    reminderDuplicate: "Напоминание на это время уже установлено.",
    reminderRemoved: "Напоминание удалено.",
    save: "Сохранить",
    cancel: "Отмена",
    remove: "Удалить",
    success: "Готово!",
    invalidReminder: "Выберите корректное время до события.",
    authRequired: "Откройте приложение из Telegram для этого действия.",
    career: "Карьера",
    computer_science: "Computer Science",
    hackathons: "Хакатоны",
    workshops: "Воркшопы",
    sport: "Спорт",
    volunteering: "Волонтерство",
    entertainment: "Развлечения",
    club_events: "Клубные события",
  },
  kk: {
    events: "Іс-шаралар",
    favorites: "Таңдаулылар",
    reminders: "Еске салулар",
    categories: "Санаттар",
    profile: "Профиль",
    unavailable: "Іс-шара қолжетімсіз.",
    loading: "Жүктелуде",
    dateTime: "Күні мен уақыты",
    location: "Орны",
    organizer: "Ұйымдастырушы",
    attendees: "Қатысушылар",
    description: "Сипаттама",
    related: "Ұқсас іс-шаралар",
    addReminder: "Еске салу",
    share: "Бөлісу",
    register: "Тіркелу",
    backToEvents: "Іс-шараларға",
    emptyFavorites: "Таңдаулы іс-шаралар жоқ.",
    emptyReminders: "Алдағы еске салулар жоқ.",
    emptyEvents: "Қазір іс-шаралар жоқ.",
    ended: "Аяқталды",
    reminderTitle: "Іс-шараға дейін хабарлау",
    reminderTimer: "КК : СС : ММ",
    reminderSetFor: "Іс-шараға дейін хабарлау",
    reminderZero: "Уақыт нөлден үлкен болуы керек.",
    reminderTooLate: "Бұл еске салуды орнату үшін тым кеш.",
    reminderDuplicate: "Бұл уақытта еске салу қойылған.",
    reminderRemoved: "Еске салу жойылды.",
    save: "Сақтау",
    cancel: "Болдырмау",
    remove: "Жою",
    success: "Дайын!",
    invalidReminder: "Іс-шараға дейінгі дұрыс уақытты таңдаңыз.",
    authRequired: "Бұл әрекет үшін Telegram ішінен ашыңыз.",
    career: "Мансап",
    computer_science: "Computer Science",
    hackathons: "Хакатондар",
    workshops: "Воркшоптар",
    sport: "Спорт",
    volunteering: "Еріктілік",
    entertainment: "Ойын-сауық",
    club_events: "Клуб іс-шаралары",
  },
};

export function t(key) {
  return dict[state.lang]?.[key] || dict.en[key] || key;
}

export function categoryLabel(category) {
  const value = String(category || "").trim();
  const key = String(category || "").trim().toLowerCase().replace(/[\s-]+/g, "_");
  const translated = t(key);
  if (translated !== key) {
    return translated;
  }
  return value
    .split(/([\s-]+)/)
    .map((part) => (/[\s-]+/.test(part) ? part : part.charAt(0).toUpperCase() + part.slice(1).toLowerCase()))
    .join("");
}

export function formatEventDate(event) {
  const value = new Date(`${event.date}T${event.time || "00:00"}:00`);
  if (Number.isNaN(value.getTime())) {
    return `${event.date} ${event.time}`;
  }
  return new Intl.DateTimeFormat(state.lang, {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(value);
}

export function formatReminderOffset(minutes) {
  const d = Math.floor(minutes / 1440);
  const h = Math.floor((minutes % 1440) / 60);
  const m = minutes % 60;
  return [
    String(d).padStart(2, "0"),
    String(h).padStart(2, "0"),
    String(m).padStart(2, "0"),
  ].join(":");
}
