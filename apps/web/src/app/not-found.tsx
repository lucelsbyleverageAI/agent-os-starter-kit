import Link from 'next/link';

export default function NotFound() {
  return (
    <div className="flex h-screen flex-col items-center justify-center">
      <h2 className="text-2xl font-semibold">404 - Page Not Found</h2>
      <p className="mt-2 text-gray-600">Could not find the requested resource</p>
      <Link
        href="/"
        className="mt-4 rounded-md bg-blue-600 px-4 py-2 text-white hover:bg-blue-700"
      >
        Return Home
      </Link>
    </div>
  );
}