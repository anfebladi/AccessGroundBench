import {
  cloneElement,
  isValidElement,
  type ReactElement,
  type ReactNode,
} from "react";
export function PageOutlet({
  active,
  children,
}: {
  active: boolean;
  children: ReactNode;
}) {
  if (!isValidElement(children)) return null;

  return cloneElement(children as ReactElement<{ hidden?: boolean }>, {
    hidden: !active,
  });
}
